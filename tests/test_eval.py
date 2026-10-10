"""Tests for mutation operators, harness, scoring, and eval reports."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from regtriage.agent import Diagnosis, LlmResponse, ReplayClient, ToolUseBlock
from regtriage.agent.tooling import SUBMIT_DIAGNOSIS
from regtriage.errors import AgentLoopError
from regtriage.eval import (
    EVAL_MODULES,
    EVAL_TARGETS,
    UPSTREAM_LICENSE_SPDX,
    UPSTREAM_PIN,
    UPSTREAM_URL,
    EvalConfig,
    EvalReport,
    MeteredClient,
    SimOutcome,
    apply_mutant,
    fabrication_rates,
    generate_mutants,
    load_eval_results,
    prepare_case,
    rank_files_heuristic,
    render_results_markdown,
    run_eval,
    same_module,
    score_diagnosis,
    summarize_manual_csv,
    write_eval_results,
)
from regtriage.eval.mutants import Mutant
from regtriage.parsing import Failure

GIT = shutil.which("git")

DUT = (
    "module dut;\n"
    "  reg [31:0] len;\n"
    "  wire en;\n"
    "  always @(posedge clk) begin\n"
    "    if (rst) len <= 0;\n"
    "    else if (en) len <= len + 1;\n"
    "    if (len == 10) done <= 1;\n"
    "  end\n"
    "endmodule\n"
)


def _diag_for(target: str, quote: str) -> dict[str, Any]:
    return {
        "cluster_id": "cluster-001",
        "root_cause_summary": "reset missing",
        "suspected_files": [{"path": target, "line_start": 2, "line_end": 2, "reason": "r"}],
        "evidence": [
            {"kind": "source", "ref": target, "line_start": 2, "line_end": 2, "quote": quote}
        ],
        "confidence": 0.9,
        "next_steps": ["fix"],
        "status": "verified",
    }


def test_operators_mutate_expected_lines() -> None:
    from regtriage.eval.mutants import (
        _flip_comparison,
        _invert_enable,
        _invert_if,
        _off_by_one_const,
        _off_by_one_width,
        _remove_reset,
    )

    assert _flip_comparison("if (a == b)") == "if (a != b)"
    assert _flip_comparison("if (a != b)") == "if (a == b)"
    assert _flip_comparison("if (a > b)") == "if (a < b)"
    assert _flip_comparison("if (a < b)") == "if (a > b)"
    assert _flip_comparison("assign x = a <= b;") is None
    assert _flip_comparison("wire x;") is None
    assert _invert_if("  if (en) begin") == "  if (!(en)) begin"
    assert _invert_if("  wire x;") is None
    assert _invert_if("  if (!en)") is None
    assert _off_by_one_const("  repeat (5) @(posedge clk);") == "  repeat (6) @(posedge clk);"
    assert _off_by_one_const("  reg [31:0] len;") is None
    assert _off_by_one_width("  reg [31:0] len;") == "  reg [32:0] len;"
    assert _off_by_one_width("  wire x;") is None
    assert _remove_reset("    if (rst) len <= 0;") == "//     if (rst) len <= 0;"
    assert _remove_reset("    wire x;") is None
    assert _invert_enable("  if (valid) begin") == "  if (!(valid)) begin"
    assert _invert_enable("  if (len == 1) begin") is None


def test_generate_is_seeded_and_capped() -> None:
    first = generate_mutants({"rtl/dut.v": DUT}, seed=7, count=3)
    second = generate_mutants({"rtl/dut.v": DUT}, seed=7, count=3)
    assert [m.model_dump() for m in first] == [m.model_dump() for m in second]
    assert len(first) == 3
    assert [m.mutant_id for m in first] == ["m0000", "m0001", "m0002"]
    assert {m.operator for m in first} != set()
    third = generate_mutants({"rtl/dut.v": DUT}, seed=8, count=3)
    assert [m.mutant_id for m in third] == ["m0000", "m0001", "m0002"]


def test_apply_mutant_replaces_line() -> None:
    mutant = Mutant(
        mutant_id="m0000",
        file="f.v",
        line=2,
        operator="flip_comparison",
        original="b",
        mutated="B",
    )
    assert apply_mutant("a\nb\nc\n", mutant) == "a\nB\nc\n"
    with pytest.raises(ValueError):
        apply_mutant("a\n", mutant.model_copy(update={"line": 9}))


def test_prepare_case_fresh_repo_and_neutral_name(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = tmp_path / "src"
    (src / "rtl").mkdir(parents=True)
    (src / "rtl" / "dut.v").write_text(DUT, encoding="utf-8")
    (src / "tb").mkdir()
    before_env = dict(os.environ)
    case = prepare_case(src, tmp_path / "work", "case-0003", {"rtl/dut.v": DUT + "// x\n"})
    assert case.name == "case-0003"
    assert (case / "rtl" / "dut.v").read_text(encoding="utf-8").endswith("// x\n")
    assert (case / ".git").is_dir()
    log = subprocess.run(
        ["git", "-C", str(case), "log", "--oneline"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert len(log.stdout.strip().splitlines()) == 1
    assert "m0000" not in str(case) and "flip_comparison" not in str(case)
    assert dict(os.environ) == before_env


def test_prepare_case_missing_repo(tmp_path: Path) -> None:
    from regtriage.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        prepare_case(tmp_path / "nope", tmp_path / "work", "case-0000", None)


def test_prepare_case_reuses_name(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    first = prepare_case(src, tmp_path / "work", "case-0000", None)
    second = prepare_case(src, tmp_path / "work", "case-0000", None)
    assert first == second and second.is_dir()


def _stub_repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "rtl").mkdir(parents=True)
    (src / "rtl" / "dut.v").write_text(DUT, encoding="utf-8")
    return src


def _stub_simulate(workdir: Path, module: str) -> SimOutcome:
    if workdir.name.startswith("base"):
        return SimOutcome(passed=True)
    return SimOutcome(
        passed=False,
        failures=[Failure(test="t0", message="mismatch in dut block", raw_excerpt="")],
    )


def _stub_factory() -> ReplayClient:
    return ReplayClient(
        [
            LlmResponse(
                content=[
                    ToolUseBlock(
                        id="s1",
                        name=SUBMIT_DIAGNOSIS,
                        input=_diag_for("rtl/dut.v", "reg [31:0] len;"),
                    )
                ],
                stop_reason="tool_use",
                input_tokens=0,
                output_tokens=0,
            )
        ]
    )


def _eval_config(src: Path, work: Path, **over: Any) -> EvalConfig:
    base: dict[str, Any] = {
        "repo_root": src,
        "modules": ["tb/dummy"],
        "target_files": ["rtl/dut.v"],
        "work_root": work,
        "seed": 7,
        "mutant_count": 2,
    }
    base.update(over)
    return EvalConfig(**base)


def test_baseline_red_aborts_without_mutating(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work"),
        lambda wd, mod: SimOutcome(passed=False),
        _stub_factory,
        pin="abc",
    )
    assert report.aborted is True
    assert "baseline" in report.abort_reason
    assert report.generated == 0 and report.used == 0


def test_full_run_scores_three_arms(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work"), _stub_simulate, _stub_factory, pin="abc"
    )
    assert report.aborted is False
    assert report.generated == 2 and report.killed == 2 and report.used == 2
    full = report.arms["full"]
    assert full.hit_file == 1.0 and full.hit_module == 1.0
    assert full.fab_before == 0.0 and full.fab_after == 0.0 and full.used == 2
    assert report.arms["no_validator"].used == 2
    assert report.arms["heuristic"].hit_file == 1.0
    assert report.arms["heuristic"].used == 2
    assert report.cost.llm_calls == 4
    assert report.cost.usd == 0.0
    assert report.mean_agent_seconds >= 0.0


def test_budget_guard_aborts_cleanly(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work", max_llm_calls=1),
        _stub_simulate,
        _stub_factory,
        pin="abc",
    )
    assert report.aborted is True
    assert "budget" in report.abort_reason


def test_surviving_mutant_not_counted(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work"),
        lambda wd, mod: SimOutcome(passed=True),
        _stub_factory,
        pin="abc",
    )
    assert report.aborted is False
    assert report.generated == 2 and report.killed == 0 and report.used == 0
    assert report.arms["heuristic"].used == 0


def test_killed_without_failures_not_scored(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work"),
        lambda wd, mod: SimOutcome(passed=wd.name.startswith("base")),
        _stub_factory,
        pin="abc",
    )
    assert report.killed == 2 and report.used == 0


def test_missing_target_is_config_error(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    from regtriage.errors import ConfigurationError

    src = _stub_repo(tmp_path)
    with pytest.raises(ConfigurationError):
        run_eval(
            _eval_config(src, tmp_path / "work", target_files=["rtl/ghost.v"]),
            _stub_simulate,
            _stub_factory,
            pin="abc",
        )


def test_cost_budget_aborts(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")

    def pricey() -> ReplayClient:
        return ReplayClient(
            [
                LlmResponse(
                    content=[
                        ToolUseBlock(
                            id="s1",
                            name=SUBMIT_DIAGNOSIS,
                            input=_diag_for("rtl/dut.v", "reg [31:0] len;"),
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=500_000,
                    output_tokens=0,
                )
            ]
        )

    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work", max_cost_usd=0.5),
        _stub_simulate,
        pricey,
        pin="abc",
    )
    assert report.aborted is True
    assert "cost budget" in report.abort_reason
    assert report.cost.usd == pytest.approx(1.0)


def test_rank_skips_git_and_unreadable(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "rtl").mkdir(parents=True)
    (root / "rtl" / "dma_engine.v").write_text("module dma_engine;\nendmodule\n", encoding="utf-8")
    (root / "rtl" / "other.v").write_text("module other;\nendmodule\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "dma_engine.v").write_text("dma engine dma engine\n", encoding="utf-8")
    (root / "weird.v").mkdir()
    ranking = rank_files_heuristic(root, "timeout in dma engine block")
    assert ranking[0] == "rtl/dma_engine.v"
    assert not any(p.startswith(".git/") for p in ranking)


def test_score_diagnosis_and_modules() -> None:
    from regtriage.agent import SuspectedFile
    from regtriage.validation import Evidence

    mutant = Mutant(mutant_id="m0", file="rtl/dut.v", line=10, operator="flip_comparison")
    good = Diagnosis(
        cluster_id="c",
        root_cause_summary="x",
        suspected_files=[SuspectedFile(path="rtl/dut.v", line_start=12, line_end=12, reason="r")],
        evidence=[
            Evidence(
                kind="commit",
                ref="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:rtl/dut.v",
                line_start=1,
                line_end=1,
                quote="q",
            )
        ],
        confidence=0.5,
        status="verified",
    )
    assert score_diagnosis(good, mutant) == {"hit_file": True, "hit_module": True, "hit_line": True}
    bad = Diagnosis(cluster_id="c", root_cause_summary="x", confidence=0.1, status="failed")
    assert score_diagnosis(bad, mutant) == {
        "hit_file": False,
        "hit_module": False,
        "hit_line": False,
    }
    assert same_module("rtl/dut.v", "rtl/other.v") is True
    assert same_module("tb/dma_if.v", "rtl/dma_if.v") is True
    assert same_module("a.v", "b.v") is False


def test_fabrication_rates(tmp_path: Path) -> None:
    from regtriage.validation import Evidence

    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("real line here\n", encoding="utf-8")
    raw = Diagnosis(
        cluster_id="c",
        root_cause_summary="x",
        evidence=[
            Evidence(kind="log", ref="sim.log", line_start=1, line_end=1, quote="real line here"),
            Evidence(kind="log", ref="sim.log", line_start=1, line_end=1, quote="invented"),
        ],
        confidence=0.5,
        status="verified",
    )
    final = raw.model_copy(update={"failed_evidence": ["evidence[1]: nope"]})
    before, after = fabrication_rates([raw], final, root)
    assert before == pytest.approx(0.5)
    assert after == pytest.approx(1 / 3)
    assert fabrication_rates([], raw, root) == (0.0, 0.0)
    blind, _ = fabrication_rates([raw], final, None)
    assert blind == 1.0


def test_report_round_trip_and_limitations(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("git not installed")
    src = _stub_repo(tmp_path)
    report = run_eval(
        _eval_config(src, tmp_path / "work"), _stub_simulate, _stub_factory, pin="abc"
    )
    out = tmp_path / "eval" / "results.json"
    write_eval_results(out, report)
    assert load_eval_results(out).pin == "abc"
    markdown = render_results_markdown(
        report, {"cases": 2.0, "mean_seconds": 120.0, "skipped": 0.0}
    )
    assert "| full |" in markdown and "simpler than" in markdown and "UVM" in markdown
    assert "Manual triage mean" in markdown
    plain = render_results_markdown(report, None)
    assert "ABORTED" not in plain and "Manual triage mean" not in plain
    empty_manual = render_results_markdown(
        report, {"cases": 0.0, "mean_seconds": 0.0, "skipped": 1.0}
    )
    assert "Manual triage mean" not in empty_manual
    aborted = report.model_copy(update={"aborted": True, "abort_reason": "red"})
    assert "ABORTED: red" in render_results_markdown(aborted, None)
    from regtriage.eval import render_row_for_readme

    assert render_row_for_readme(report)["full"]["used"] == 2


def test_manual_csv_summary(tmp_path: Path) -> None:
    csv_path = tmp_path / "manual.csv"
    csv_path.write_text(
        "case_id,file,operator,manual_seconds,notes\nm0000,f.v,flip_comparison,60,x\nm0001,f.v,invert_if,,todo\nm0002,f.v,invert_if,abc,bad\n",
        encoding="utf-8",
    )
    summary = summarize_manual_csv(csv_path)
    assert summary == {"cases": 1.0, "mean_seconds": 60.0, "skipped": 2.0}
    empty = tmp_path / "e.csv"
    empty.write_text("case_id,file,operator,manual_seconds,notes\n", encoding="utf-8")
    assert summarize_manual_csv(empty)["mean_seconds"] == 0.0
    from regtriage.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="manual timing csv"):
        summarize_manual_csv(tmp_path / "missing.csv")


def test_metered_client_cost_guard() -> None:
    from regtriage.agent import LlmRequest
    from regtriage.errors import AgentLoopError

    inner = ReplayClient(
        [LlmResponse(content=[], stop_reason="end_turn", input_tokens=1_000_000, output_tokens=0)]
    )
    metered = MeteredClient(inner)
    metered.create_message(LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={}))
    assert metered.usd == pytest.approx(2.0)
    with pytest.raises(AgentLoopError, match="cost budget"):
        metered.check_budget(10, 1.0)
    with pytest.raises(AgentLoopError, match="call budget"):
        metered.check_budget(1, 100.0)
    metered.check_budget(10, 100.0)


def test_make_simulate_outcomes(tmp_path: Path) -> None:
    if shutil.which("make") is None:
        pytest.skip("make not installed")
    if GIT is None:
        pytest.skip("git not installed")
    from regtriage.eval import make_simulate
    from regtriage.runner import LocalExecutor

    pass_xml = '<?xml version="1.0"?><testsuite><testcase classname="c" name="n" /></testsuite>'
    fail_xml = (
        '<?xml version="1.0"?><testsuite><testcase classname="c" name="n">'
        '<failure message="boom">trace</failure></testcase></testsuite>'
    )
    work = tmp_path / "work"
    for name, recipe in (
        ("pass", f"printf '%s' '{pass_xml}' > results.xml"),
        ("fail", f"printf '%s' '{fail_xml}' > results.xml; exit 1"),
        ("noxml", "true"),
    ):
        mod = work / name / "tb" / "m"
        mod.mkdir(parents=True)
        (mod / "Makefile").write_text(f"all:\n\t{recipe}\n", encoding="utf-8")
    simulate = make_simulate(LocalExecutor(max_parallel=1), 60.0)
    assert simulate(work / "pass", "tb/m").passed is True
    failed = simulate(work / "fail", "tb/m")
    assert failed.passed is False and len(failed.failures) == 1
    assert simulate(work / "noxml", "tb/m").passed is False
    inner = ReplayClient(
        [
            LlmResponse(
                content=[], stop_reason="end_turn", input_tokens=1_000_000, output_tokens=500_000
            )
        ]
    )
    from regtriage.agent import LlmRequest

    metered = MeteredClient(inner)
    metered.check_budget(5, 100.0)
    metered.create_message(LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={}))
    assert metered.llm_calls == 1
    assert metered.usd == pytest.approx(2.0 + 5.0)
    with pytest.raises(AgentLoopError, match="budget"):
        metered.check_budget(1, 100.0)


def test_upstream_pin_facts() -> None:
    assert UPSTREAM_URL == "https://github.com/alexforencich/verilog-pcie.git"
    assert len(UPSTREAM_PIN) == 40 and all(c in "0123456789abcdef" for c in UPSTREAM_PIN)
    assert UPSTREAM_LICENSE_SPDX == "MIT"
    assert len(EVAL_MODULES) >= 3 and len(EVAL_TARGETS) >= 3
    assert any(m.startswith("tb/") for m in EVAL_MODULES)
    assert all(t.startswith("rtl/") and t.endswith(".v") for t in EVAL_TARGETS)


def test_eval_report_model_defaults() -> None:
    report = EvalReport(pin="x", seed=0, modules=["m"], target_files=["f"], baseline=[])
    assert report.aborted is False and report.arms == {} and report.cost.llm_calls == 0


def test_results_json_load_failure(tmp_path: Path) -> None:
    from regtriage.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        load_eval_results(tmp_path / "missing.json")
