"""Eval result persistence, RESULTS.md generation, and manual-timing math."""

import csv
from pathlib import Path
from typing import Any

from regtriage.errors import ConfigurationError
from regtriage.eval.harness import EvalReport

LIMITATIONS = (
    "Known limitations: mutants are small syntactic changes, simpler than "
    "real protocol-level PCIe bugs, so hit rates overstate real-world "
    "accuracy; real UVM and commercial-simulator logs are not covered beyond "
    "the sample parsers; numbers below come from this harness run only."
)


def write_eval_results(path: Path, report: EvalReport) -> None:
    """Write the report verbatim as indented JSON (the README table source)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_eval_results(path: Path) -> EvalReport:
    """Load a previously written results.json."""
    try:
        return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"cannot load eval results: {path} ({exc})") from exc


def summarize_manual_csv(path: Path) -> dict[str, float]:
    """Summarize human stopwatch entries; blank/bad rows are counted, not used.

    Never fabricates: with no usable rows the mean is 0.0 and cases is 0.
    """
    cases = 0
    total = 0.0
    skipped = 0
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                cell = (row.get("manual_seconds") or "").strip()
                try:
                    total += float(cell)
                except ValueError:
                    skipped += 1
                    continue
                cases += 1
    except OSError as exc:
        raise ConfigurationError(f"cannot read manual timing csv: {path} ({exc})") from exc
    return {
        "cases": float(cases),
        "mean_seconds": (total / cases) if cases else 0.0,
        "skipped": float(skipped),
    }


def render_results_markdown(report: EvalReport, manual: dict[str, float] | None = None) -> str:
    """Render results.json as docs/RESULTS.md, limitations included."""
    lines = [
        "# RegTriage eval results",
        "",
        f"Upstream pin: `{report.pin}` — seed {report.seed}",
        f"Modules: {', '.join(report.modules)}",
        f"Baseline: {sum(1 for b in report.baseline if b.passed)}/{len(report.baseline)} green",
        f"Mutants: generated {report.generated}, killed {report.killed}, used {report.used}",
        "",
        "| arm | hit@file | hit@module | hit@line(±5) | fab before | fab after | used |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in ("heuristic", "no_validator", "full"):
        arm = report.arms.get(name)
        if arm is None:
            continue
        lines.append(
            f"| {name} | {arm.hit_file:.2f} | {arm.hit_module:.2f} | {arm.hit_line:.2f} "
            f"| {arm.fab_before:.2f} | {arm.fab_after:.2f} | {arm.used} |"
        )
    lines += [
        "",
        f"Cost: {report.cost.llm_calls} LLM calls, "
        f"{report.cost.input_tokens} in / {report.cost.output_tokens} out tokens, "
        f"${report.cost.usd:.4f}; mean agent time {report.mean_agent_seconds:.1f}s",
    ]
    if report.aborted:
        lines.append(f"ABORTED: {report.abort_reason}")
    if manual is not None and manual.get("cases", 0) > 0:
        saved = manual["mean_seconds"] - report.mean_agent_seconds
        lines.append(
            f"Manual triage mean: {manual['mean_seconds']:.1f}s over "
            f"{int(manual['cases'])} cases; estimated saved per case: {saved:.1f}s"
        )
    lines += ["", LIMITATIONS, ""]
    return "\n".join(lines)


def render_row_for_readme(report: EvalReport) -> dict[str, Any]:
    """Flatten arm means for README table generation (scripts read results.json)."""
    return {
        arm: {
            "hit_file": scores.hit_file,
            "hit_module": scores.hit_module,
            "hit_line": scores.hit_line,
            "fab_before": scores.fab_before,
            "fab_after": scores.fab_after,
            "used": scores.used,
        }
        for arm, scores in report.arms.items()
    }
