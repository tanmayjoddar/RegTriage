"""Eval harness: baseline, seeded mutants on temp copies, arms, cost guard."""

import os
import re
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from regtriage.agent import Diagnosis, LlmClient, triage_cluster
from regtriage.agent.protocol import LlmRequest, LlmResponse
from regtriage.config import DEFAULT_MODEL_ID, RegTriageConfig
from regtriage.errors import (
    AgentLoopError,
    BudgetExceeded,
    ConfigurationError,
    ExecutionError,
    ParsingError,
)
from regtriage.eval.mutants import Mutant, apply_mutant, generate_mutants
from regtriage.eval.scoring import fabrication_rates, same_module, score_diagnosis
from regtriage.parsing import CocotbResultsParser, Failure
from regtriage.runner import JobSpec, LocalExecutor
from regtriage.signature import cluster_failures
from regtriage.tools import run_git

INPUT_USD_PER_MTOK = 2.0
OUTPUT_USD_PER_MTOK = 10.0


class SimOutcome(BaseModel):
    """One simulation: pass/fail plus parsed failures (empty when infra fails)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    failures: list[Failure] = Field(default_factory=list)


SimulateFn = Callable[[Path, str], SimOutcome]
ClientFactory = Callable[[], LlmClient]


class EvalConfig(BaseModel):
    """Everything an eval run needs; modules are tb dirs, targets are .v files."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_root: Path
    modules: list[str] = Field(min_length=1)
    target_files: list[str] = Field(min_length=1)
    work_root: Path
    seed: int = 0
    mutant_count: int = Field(default=30, ge=1)
    sim_timeout_seconds: float = Field(default=600.0, gt=0)
    max_llm_calls: int = Field(default=200, ge=1)
    max_cost_usd: float = Field(default=20.0, ge=0)
    model_id: str = DEFAULT_MODEL_ID
    similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_agent_steps: int = Field(default=8, ge=1, le=50)
    token_ceiling: int = Field(default=100_000, gt=0)


class BaselineResult(BaseModel):
    """One module's pristine-tree simulation outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str
    passed: bool
    failure_count: int = Field(ge=0)


class ArmScores(BaseModel):
    """Mean scores for one arm over the used (killed + triaged) mutants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    arm: str
    hit_file: float = Field(ge=0.0, le=1.0)
    hit_module: float = Field(ge=0.0, le=1.0)
    hit_line: float = Field(ge=0.0, le=1.0)
    fab_before: float = Field(ge=0.0, le=1.0)
    fab_after: float = Field(ge=0.0, le=1.0)
    used: int = Field(ge=0)


class CostRecord(BaseModel):
    """Metered LLM spend for the whole eval run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    usd: float = Field(ge=0.0)


class EvalReport(BaseModel):
    """Complete eval outcome; written verbatim to eval/results.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pin: str
    seed: int
    modules: list[str]
    target_files: list[str]
    baseline: list[BaselineResult]
    generated: int = Field(default=0, ge=0)
    killed: int = Field(default=0, ge=0)
    used: int = Field(default=0, ge=0)
    arms: dict[str, ArmScores] = Field(default_factory=dict)
    cost: CostRecord = CostRecord(llm_calls=0, input_tokens=0, output_tokens=0, usd=0.0)
    mean_agent_seconds: float = Field(default=0.0, ge=0.0)
    aborted: bool = False
    abort_reason: str = ""


class MeteredClient:
    """Count calls/tokens/usd around any client; block over-budget sends.

    Ceilings are checked BEFORE forwarding, so a blocked call never leaves
    the machine and never spends. Breaches raise BudgetExceeded.
    """

    def __init__(self, inner: LlmClient, max_calls: int, max_usd: float) -> None:
        if max_calls < 1:
            raise ConfigurationError(
                f"max_calls must be at least 1, got {max_calls}", parameter_name="max_calls"
            )
        if max_usd < 0:
            raise ConfigurationError(
                f"max_usd must not be negative, got {max_usd}", parameter_name="max_usd"
            )
        self._inner = inner
        self._max_calls = max_calls
        self._max_usd = max_usd
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def usd(self) -> float:
        """Spend so far at current Sonnet pricing."""
        return (
            self.input_tokens / 1_000_000 * INPUT_USD_PER_MTOK
            + self.output_tokens / 1_000_000 * OUTPUT_USD_PER_MTOK
        )

    def check_budget(self, max_calls: int, max_usd: float) -> None:
        """Raise BudgetExceeded when either ceiling is already reached."""
        if self.llm_calls >= max_calls:
            raise BudgetExceeded(f"LLM call budget exceeded ({max_calls} calls)")
        if self.usd >= max_usd:
            raise BudgetExceeded(f"cost budget exceeded (${self.usd:.4f} >= ${max_usd:.2f})")

    def create_message(self, request: LlmRequest) -> LlmResponse:
        """Block over-budget calls before sending, then meter the response."""
        self.check_budget(self._max_calls, self._max_usd)
        self.llm_calls += 1
        response = self._inner.create_message(request)
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        return response


def make_simulate(executor: LocalExecutor, timeout_seconds: float) -> SimulateFn:
    """Build the production simulator: `make` in the module dir + XML parse."""
    parser = CocotbResultsParser()

    def simulate(workdir: Path, module: str) -> SimOutcome:
        try:
            (result,) = executor.run_jobs(
                [
                    JobSpec(
                        job_id=module,
                        argv=["make"],
                        cwd=workdir / module,
                        timeout_seconds=timeout_seconds,
                    )
                ]
            )
        except ExecutionError:
            return SimOutcome(passed=False)
        try:
            failures = parser.parse(workdir / module / "results.xml")
        except ParsingError:
            return SimOutcome(passed=False)
        if result.returncode != 0 or result.timed_out or failures:
            return SimOutcome(passed=False, failures=failures)
        return SimOutcome(passed=True)

    return simulate


def _remove_tree(path: Path) -> None:
    """rmtree that clears read-only flags first (git objects on Windows)."""

    def _make_writable(func: Callable[..., Any], target: str, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=_make_writable)


def prepare_case(
    repo_root: Path, work_root: Path, name: str, mutations: dict[str, str] | None
) -> Path:
    """Copy the tree (minus .git), apply mutant text, re-init a fresh repo.

    The single squashed commit carries no upstream history, so git_blame /
    git_log reveal nothing about the original project. `name` must be a
    neutral case label (never a mutant id, file, or operator).
    """
    if not repo_root.is_dir():
        raise ConfigurationError(
            f"eval repo root is not a directory: {repo_root}", parameter_name="repo_root"
        )
    dest = work_root / name
    if dest.exists():
        _remove_tree(dest)
    shutil.copytree(repo_root, dest, ignore=shutil.ignore_patterns(".git"))
    for rel, text in (mutations or {}).items():
        (dest / rel).write_text(text, encoding="utf-8")
    run_git(work_root, ["init", "-q", str(dest)], 60.0)
    run_git(dest, ["add", "-A"], 60.0)
    run_git(
        dest,
        [
            "-c",
            "user.name=RegTriage Eval",
            "-c",
            "user.email=eval@example.com",
            "commit",
            "-q",
            "-m",
            "eval snapshot",
        ],
        60.0,
    )
    return dest


def rank_files_heuristic(root: Path, message: str, limit: int = 5) -> list[str]:
    """Rank .v files by identifier overlap with the failure message.

    No LLM, no validator: the no-LLM baseline arm. Ties break by path so the
    ranking is deterministic.
    """
    tokens = {t for t in re.findall(r"[a-z0-9_]+", message.lower()) if len(t) >= 3}
    scored: list[tuple[int, str]] = []
    for path in sorted(root.rglob("*.v")):
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        scored.append(
            (sum(text.count(token) for token in tokens), path.relative_to(root).as_posix())
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [rel for _, rel in scored[:limit]]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_eval(
    config: EvalConfig, simulate: SimulateFn, make_client: ClientFactory, pin: str
) -> EvalReport:
    """Run baseline, mutants, and three arms; abort cleanly on red baseline
    or exhausted budgets. Only killed mutants with a triageable cluster score."""
    config.work_root.mkdir(parents=True, exist_ok=True)
    baseline: list[BaselineResult] = []
    for index, module in enumerate(config.modules):
        case = prepare_case(config.repo_root, config.work_root, f"base-{index:04d}", None)
        outcome = simulate(case, module)
        baseline.append(
            BaselineResult(
                module=module, passed=outcome.passed, failure_count=len(outcome.failures)
            )
        )
    skeleton = EvalReport(
        pin=pin,
        seed=config.seed,
        modules=list(config.modules),
        target_files=list(config.target_files),
        baseline=baseline,
        arms={
            name: ArmScores(
                arm=name, hit_file=0, hit_module=0, hit_line=0, fab_before=0, fab_after=0, used=0
            )
            for name in ("heuristic", "no_validator", "full")
        },
    )
    if not all(item.passed for item in baseline):
        return skeleton.model_copy(
            update={"aborted": True, "abort_reason": "baseline not green; refusing to mutate"}
        )
    sources: dict[str, str] = {}
    for rel in config.target_files:
        path = config.repo_root / rel
        if not path.is_file():
            raise ConfigurationError(f"eval target not found: {rel}", parameter_name="target_files")
        sources[rel] = path.read_text(encoding="utf-8", errors="replace")
    mutants = generate_mutants(sources, config.seed, config.mutant_count)
    budget = _Budget()
    heuristic_hits: list[dict[str, bool]] = []
    scored: dict[str, list[tuple[dict[str, bool], float, float]]] = {
        "no_validator": [],
        "full": [],
    }
    agent_seconds: list[float] = []
    killed = 0
    used = 0
    for index, mutant in enumerate(mutants):
        case = prepare_case(
            config.repo_root,
            config.work_root,
            f"case-{index:04d}",
            {mutant.file: apply_mutant(sources[mutant.file], mutant)},
        )
        failing: list[tuple[str, list[Failure]]] = []
        for module in config.modules:
            outcome = simulate(case, module)
            if not outcome.passed:
                failing.append((module, outcome.failures))
        if not failing:
            continue
        killed += 1
        clusters = cluster_failures(failing[0][1], config.similarity_threshold)
        if not clusters:
            continue
        used += 1
        cluster = clusters[0]
        message = cluster.members[0].message
        ranking = rank_files_heuristic(case, message)
        top = ranking[0] if ranking else ""
        heuristic_hits.append(
            {
                "hit_file": top == mutant.file,
                "hit_module": bool(top) and same_module(top, mutant.file),
                "hit_line": False,
            }
        )
        try:
            for arm, skip in (("no_validator", True), ("full", False)):
                budget.check(config.max_llm_calls, config.max_cost_usd)
                metered = MeteredClient(make_client(), config.max_llm_calls, config.max_cost_usd)
                captured: list[Diagnosis] = []
                agent_config = RegTriageConfig(
                    workspace_root=case,
                    model_id=config.model_id,
                    max_agent_steps=config.max_agent_steps,
                    token_ceiling=config.token_ceiling,
                )
                started = time.monotonic()
                try:
                    diagnosis = triage_cluster(
                        client=metered,
                        config=agent_config,
                        root=case,
                        cluster=cluster,
                        skip_validation=skip,
                        capture=captured,
                    )
                finally:
                    agent_seconds.append(time.monotonic() - started)
                budget.absorb(metered)
                budget.check(config.max_llm_calls, config.max_cost_usd)
                before, _ = fabrication_rates(captured, diagnosis, case)
                _, after = fabrication_rates([], diagnosis, None)
                scored[arm].append((score_diagnosis(diagnosis, mutant), before, after))
        except AgentLoopError as exc:
            return _finish(
                skeleton,
                mutants,
                killed,
                used,
                heuristic_hits,
                scored,
                budget,
                agent_seconds,
                aborted=True,
                abort_reason=str(exc),
            )
    return _finish(skeleton, mutants, killed, used, heuristic_hits, scored, budget, agent_seconds)


class _Budget:
    """Mutable spend counters shared across metered arm clients."""

    def __init__(self) -> None:
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def usd(self) -> float:
        """Spend so far at current Sonnet pricing."""
        return (
            self.input_tokens / 1_000_000 * INPUT_USD_PER_MTOK
            + self.output_tokens / 1_000_000 * OUTPUT_USD_PER_MTOK
        )

    def check(self, max_calls: int, max_usd: float) -> None:
        """Raise BudgetExceeded once a ceiling is reached."""
        if self.llm_calls >= max_calls:
            raise BudgetExceeded(f"LLM call budget exceeded ({max_calls} calls)")
        if self.usd >= max_usd:
            raise BudgetExceeded(f"cost budget exceeded (${self.usd:.4f} >= ${max_usd:.2f})")

    def absorb(self, metered: MeteredClient) -> None:
        """Fold one attempt's metered usage into the shared totals."""
        self.llm_calls += metered.llm_calls
        self.input_tokens += metered.input_tokens
        self.output_tokens += metered.output_tokens


def _finish(
    skeleton: EvalReport,
    mutants: list[Mutant],
    killed: int,
    used: int,
    heuristic_hits: list[dict[str, bool]],
    scored: dict[str, list[tuple[dict[str, bool], float, float]]],
    budget: _Budget,
    agent_seconds: list[float],
    aborted: bool = False,
    abort_reason: str = "",
) -> EvalReport:
    """Assemble the final report with mean arm scores and spend."""
    arms = dict(skeleton.arms)
    if heuristic_hits:
        arms["heuristic"] = ArmScores(
            arm="heuristic",
            hit_file=_mean([1.0 if h["hit_file"] else 0.0 for h in heuristic_hits]),
            hit_module=_mean([1.0 if h["hit_module"] else 0.0 for h in heuristic_hits]),
            hit_line=0.0,
            fab_before=0.0,
            fab_after=0.0,
            used=len(heuristic_hits),
        )
    for arm, rows in scored.items():
        if rows:
            arms[arm] = ArmScores(
                arm=arm,
                hit_file=_mean([1.0 if r[0]["hit_file"] else 0.0 for r in rows]),
                hit_module=_mean([1.0 if r[0]["hit_module"] else 0.0 for r in rows]),
                hit_line=_mean([1.0 if r[0]["hit_line"] else 0.0 for r in rows]),
                fab_before=_mean([r[1] for r in rows]),
                fab_after=_mean([r[2] for r in rows]),
                used=len(rows),
            )
    return skeleton.model_copy(
        update={
            "generated": len(mutants),
            "killed": killed,
            "used": used,
            "arms": arms,
            "cost": CostRecord(
                llm_calls=budget.llm_calls,
                input_tokens=budget.input_tokens,
                output_tokens=budget.output_tokens,
                usd=budget.usd,
            ),
            "mean_agent_seconds": _mean(agent_seconds),
            "aborted": aborted,
            "abort_reason": abort_reason,
        }
    )
