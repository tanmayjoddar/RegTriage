"""Typer CLI: run, report, eval, eval-report, validate-config."""

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import SecretStr

from regtriage.agent import AnthropicClient, Diagnosis, LlmClient, ReplayClient, triage_cluster
from regtriage.agent.gemini import GeminiClient
from regtriage.audit import AuditLogger
from regtriage.config import RegTriageConfig, load_config
from regtriage.errors import ConfigurationError, RegTriageError
from regtriage.eval import (
    EVAL_MODULES,
    EVAL_TARGETS,
    UPSTREAM_PIN,
    EvalConfig,
    load_eval_results,
    make_simulate,
    render_results_markdown,
    run_eval,
    summarize_manual_csv,
    write_eval_results,
)
from regtriage.logging import configure_logging
from regtriage.parsing import CocotbResultsParser
from regtriage.report import build_json_report, render_markdown, send_slack
from regtriage.runner import LocalExecutor
from regtriage.signature import cluster_failures

app = typer.Typer(no_args_is_help=True)


def _make_eval_client(offline: bool, api_key: SecretStr | None) -> LlmClient:
    """Replay for offline/keyless runs, live client otherwise (no network here)."""
    if offline or api_key is None:
        return ReplayClient([])
    return AnthropicClient(api_key)


def _make_gemini_eval_client(offline: bool, api_key: SecretStr | None) -> LlmClient:
    """Replay for offline/keyless runs, live Gemini client otherwise."""
    if offline or api_key is None:
        return ReplayClient([])
    return GeminiClient(api_key)


def _make_provider_client(config: RegTriageConfig, offline: bool) -> LlmClient:
    """Build the live client for the configured provider (no network here)."""
    if offline:
        return ReplayClient([])
    if config.provider == "gemini":
        if config.gemini_api_key is None:
            typer.echo("set GEMINI_API_KEY (or GOOGLE_API_KEY) or use --offline", err=True)
            raise typer.Exit(code=2)
        return GeminiClient(config.gemini_api_key)
    if config.anthropic_api_key is None:
        typer.echo("set ANTHROPIC_API_KEY or use --offline", err=True)
        raise typer.Exit(code=2)
    return AnthropicClient(config.anthropic_api_key)


def _active_model_id(config: RegTriageConfig) -> str:
    """Return the model id for the configured provider (config-only ids)."""
    if config.provider == "gemini":
        return config.gemini_model_id
    return config.model_id


def _load_config_or_exit(overrides: dict[str, Any] | None = None) -> RegTriageConfig:
    """Load config; print the problem and exit 2 on failure."""
    try:
        return load_config(overrides=overrides)
    except RegTriageError as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def validate_config() -> None:
    """Load configuration from env/CLI and print the masked summary."""
    config = _load_config_or_exit()
    typer.echo(json.dumps(config.mask_for_logging(), indent=2, sort_keys=True))


@app.command()
def run(
    repo: Annotated[Path, typer.Option(help="Pinned checkout to triage")],
    results_xml: Annotated[Path, typer.Option(help="cocotb results.xml")],
    out: Annotated[Path, typer.Option(help="Output directory for reports")] = Path("out"),
    offline: Annotated[bool, typer.Option(help="Log requests without sending")] = False,
    audit_log: Annotated[Path | None, typer.Option(help="JSONL audit path")] = None,
    notify_slack: Annotated[bool, typer.Option("--slack", help="POST Markdown to Slack")] = False,
) -> None:
    """Parse, cluster, triage every cluster, and write JSON + Markdown reports."""
    config = _load_config_or_exit(
        {"repo_path": repo, "results_xml_path": results_xml, "offline_mode": offline}
    )
    # Requests carry config.model_id, so point it at the active provider's
    # config-only model id (reports and audit stay consistent too).
    config = config.model_copy(update={"model_id": _active_model_id(config)})
    configure_logging(config.log_level)
    root = config.repo_path
    assert root is not None
    failures = CocotbResultsParser().parse(config.results_xml_path or results_xml)
    clusters = cluster_failures(failures, config.similarity_threshold)
    client = _make_provider_client(config, offline)
    model_id = config.model_id
    audit = AuditLogger(audit_log or (out / "audit.jsonl"))
    diagnoses: dict[str, Diagnosis] = {}
    for cluster in clusters:
        diagnoses[cluster.cluster_id] = triage_cluster(
            client=client, config=config, root=root, cluster=cluster, audit=audit, offline=offline
        )
    out.mkdir(parents=True, exist_ok=True)
    payload = build_json_report(clusters, diagnoses, model_id)
    (out / "run.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown = render_markdown(payload)
    (out / "report.md").write_text(markdown, encoding="utf-8")
    if notify_slack:
        raw = os.environ.get("SLACK_WEBHOOK_URL", "")
        if not raw.strip():
            typer.echo("set SLACK_WEBHOOK_URL or drop --slack", err=True)
            raise typer.Exit(code=2)
        send_slack(SecretStr(raw.strip()), markdown)
    counts = {"verified": 0, "unverified": 0, "failed": 0}
    for diagnosis in diagnoses.values():
        counts[diagnosis.status] += 1
    typer.echo(f"clusters={len(clusters)} " + " ".join(f"{k}={v}" for k, v in counts.items()))


@app.command()
def report(
    report_json: Annotated[Path, typer.Option(help="run.json from `run`")],
    out_md: Annotated[Path, typer.Option(help="Markdown destination")] = Path("report.md"),
) -> None:
    """Re-render Markdown from a saved JSON report."""
    try:
        payload = json.loads(report_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"cannot load report: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not isinstance(payload, dict):
        typer.echo("report JSON must be an object", err=True)
        raise typer.Exit(code=2)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(payload), encoding="utf-8")
    typer.echo(f"wrote {out_md}")


@app.command()
def eval(
    repo: Annotated[Path, typer.Option(help="Pinned upstream checkout")],
    work: Annotated[Path, typer.Option(help="Scratch dir for case copies")] = Path("eval-work"),
    mutants: Annotated[int, typer.Option(min=1, help="Mutants to generate")] = 30,
    seed: Annotated[int, typer.Option(help="RNG seed")] = 0,
    max_llm_calls: Annotated[int, typer.Option(min=1)] = 200,
    max_cost: Annotated[float, typer.Option(min=0)] = 20.0,
    offline: Annotated[bool, typer.Option(help="Log LLM requests without sending")] = False,
    out: Annotated[Path, typer.Option(help="results.json destination")] = Path("eval/results.json"),
    modules: Annotated[list[str] | None, typer.Option(help="tb dirs (repeatable)")] = None,
    targets: Annotated[list[str] | None, typer.Option(help="rtl files (repeatable)")] = None,
) -> None:
    """Run the mutation-testing eval harness (baseline, mutants, three arms)."""
    config = _load_config_or_exit()
    harness_config = EvalConfig(
        repo_root=repo,
        modules=list(modules) if modules else list(EVAL_MODULES),
        target_files=list(targets) if targets else list(EVAL_TARGETS),
        work_root=work,
        seed=seed,
        mutant_count=mutants,
        max_llm_calls=max_llm_calls,
        max_cost_usd=max_cost,
        model_id=_active_model_id(config),
        similarity_threshold=config.similarity_threshold,
        max_agent_steps=config.max_agent_steps,
        token_ceiling=config.token_ceiling,
    )
    executor = LocalExecutor(
        max_parallel=2, default_timeout_seconds=harness_config.sim_timeout_seconds
    )
    simulate = make_simulate(executor, harness_config.sim_timeout_seconds)

    def factory() -> LlmClient:
        if config.provider == "gemini":
            return _make_gemini_eval_client(offline, config.gemini_api_key)
        return _make_eval_client(offline, config.anthropic_api_key)

    try:
        result = run_eval(harness_config, simulate, factory, UPSTREAM_PIN)
    except RegTriageError as exc:
        typer.echo(f"eval failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    write_eval_results(out, result)
    typer.echo(
        f"generated={result.generated} killed={result.killed} used={result.used} "
        f"aborted={result.aborted} cost=${result.cost.usd:.4f}"
    )


@app.command(name="eval-report")
def eval_report(
    results: Annotated[Path, typer.Option(help="eval/results.json")] = Path("eval/results.json"),
    out_md: Annotated[Path, typer.Option(help="Markdown destination")] = Path("docs/RESULTS.md"),
    manual_csv: Annotated[Path | None, typer.Option(help="Stopwatch CSV")] = None,
) -> None:
    """Render docs/RESULTS.md from results.json (plus optional manual times)."""
    try:
        report = load_eval_results(results)
    except ConfigurationError as exc:
        typer.echo(f"cannot load results: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    manual = summarize_manual_csv(manual_csv) if manual_csv is not None else None
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_results_markdown(report, manual), encoding="utf-8")
    typer.echo(f"wrote {out_md}")
