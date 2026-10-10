"""Hit scoring and fabricated-citation rates for eval diagnoses."""

from pathlib import Path

from regtriage.agent import Diagnosis
from regtriage.errors import SandboxViolationError, ValidationError
from regtriage.eval.mutants import Mutant
from regtriage.validation import validate_evidence


def _cited_files(diagnosis: Diagnosis) -> list[str]:
    """Collect every file path a diagnosis points at."""
    paths = [item.path for item in diagnosis.suspected_files]
    for item in diagnosis.evidence:
        if item.kind in ("log", "source"):
            paths.append(item.ref)
    return paths


def _cited_lines(diagnosis: Diagnosis) -> list[int]:
    """Collect every cited line_start from files and evidence."""
    lines = [item.line_start for item in diagnosis.suspected_files]
    lines += [item.line_start for item in diagnosis.evidence if item.kind in ("log", "source")]
    return lines


def _stem(path: str) -> str:
    """File name without directory or extension."""
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def same_module(a: str, b: str) -> bool:
    """Match on parent directory or file stem (no extension)."""
    parent_a = a.rsplit("/", 1)[0] if "/" in a else ""
    parent_b = b.rsplit("/", 1)[0] if "/" in b else ""
    return (parent_a != "" and parent_a == parent_b) or _stem(a) == _stem(b)


def score_diagnosis(diagnosis: Diagnosis, mutant: Mutant) -> dict[str, bool]:
    """Score file / module / line(+-5) hits of one diagnosis vs ground truth."""
    files = _cited_files(diagnosis)
    lines = _cited_lines(diagnosis)
    return {
        "hit_file": mutant.file in files,
        "hit_module": any(same_module(path, mutant.file) for path in files),
        "hit_line": any(abs(line - mutant.line) <= 5 for line in lines),
    }


def fabrication_rates(
    submitted: list[Diagnosis], final: Diagnosis, root: Path | None = None
) -> tuple[float, float]:
    """(before, after) fabricated-citation rates.

    Before: fraction of evidence in raw pre-validation submissions that fails
    the machine checker (needs a root; without one every item counts failed).
    After: failed_evidence share of the final diagnosis (lists + evidence).
    Empty totals score 0.0.
    """
    checked = 0
    failed = 0
    if root is not None:
        for diagnosis in submitted:
            for item in diagnosis.evidence:
                checked += 1
                try:
                    validate_evidence(root, item)
                except (ValidationError, SandboxViolationError):
                    failed += 1
    else:
        for diagnosis in submitted:
            failed += len(diagnosis.evidence)
            checked += len(diagnosis.evidence)
    before = failed / checked if checked else 0.0
    total_after = len(final.evidence) + len(final.failed_evidence)
    after = len(final.failed_evidence) / total_after if total_after else 0.0
    return (before, after)
