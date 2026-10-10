"""Machine-checked validation of agent evidence citations.

Every check raises `ValidationError` carrying the exact reason so the agent
loop can feed it back verbatim. Nothing is silently dropped or accepted.
Files are decoded with `errors="replace"`, the same rule as the read tools,
so a quote the tools returned always matches the same bytes here.
"""

import re
from pathlib import Path

from regtriage.errors import ExecutionError, ValidationError
from regtriage.tools.git import run_git
from regtriage.tools.sandbox import resolve_within_root
from regtriage.validation.evidence import Evidence

_WS_RE = re.compile(r"\s+")
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_GIT_TIMEOUT_SECONDS = 30.0


def normalize_quote(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends."""
    return _WS_RE.sub(" ", text).strip()


def _fail(evidence: Evidence, reason: str) -> ValidationError:
    """Build a citation failure carrying kind, ref, and the exact reason."""
    return ValidationError(
        f"evidence rejected ({evidence.kind} {evidence.ref!r} "
        f"lines {evidence.line_start}-{evidence.line_end}): {reason}",
        citation_kind=evidence.kind,
        citation_ref=evidence.ref,
        reason=reason,
    )


def _read_window(path: Path, evidence: Evidence) -> str:
    """Return the normalized text of the cited line window."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _fail(evidence, f"cannot read file: {exc}") from exc
    lines = data.decode("utf-8", errors="replace").splitlines()
    if evidence.line_end > len(lines):
        raise _fail(
            evidence,
            f"lines {evidence.line_start}-{evidence.line_end} exceed file length {len(lines)}",
        )
    return normalize_quote(" ".join(lines[evidence.line_start - 1 : evidence.line_end]))


def _check_quote(evidence: Evidence, window: str) -> None:
    """Require a non-empty quote that appears verbatim in the window."""
    quote = normalize_quote(evidence.quote)
    if not quote:
        raise _fail(evidence, "quote is empty after whitespace normalization")
    if quote not in window:
        raise _fail(evidence, "normalized quote was not found in the cited lines")


def _validate_file_citation(root: Path, evidence: Evidence) -> None:
    """Validate a log/source citation against file lines on disk."""
    resolved = resolve_within_root(root, evidence.ref)
    if not resolved.is_file():
        raise _fail(evidence, f"path is not a file inside the root: {evidence.ref}")
    window = _read_window(resolved, evidence)
    _check_quote(evidence, window)


def _split_commit_ref(evidence: Evidence) -> tuple[str, str]:
    """Split a commit ref into (sha, repo-relative path) or raise."""
    sha, sep, rel = evidence.ref.partition(":")
    if not sep or not _SHA_RE.fullmatch(sha) or not rel or rel.startswith("/"):
        raise _fail(
            evidence,
            "commit ref must look like <40-hex-sha>:<repo-relative-path>",
        )
    return sha, rel


def _validate_commit_citation(
    root: Path, evidence: Evidence, timeout_seconds: float = _GIT_TIMEOUT_SECONDS
) -> None:
    """Validate a commit citation: sha exists and touched the cited file."""
    sha, rel = _split_commit_ref(evidence)
    resolved_root = resolve_within_root(root, ".")
    resolve_within_root(root, rel)
    try:
        run_git(resolved_root, ["cat-file", "-e", sha], timeout_seconds)
    except ExecutionError as exc:
        if exc.returncode is None:
            # Git itself failed (missing binary, timeout): operational error,
            # not a citation verdict, so let it propagate unchanged.
            raise
        raise _fail(evidence, f"commit sha does not exist: {sha}") from exc
    touched = run_git(
        resolved_root, ["show", "--name-only", "--format=", sha], timeout_seconds
    ).splitlines()
    if rel not in [line.strip() for line in touched if line.strip()]:
        raise _fail(evidence, f"commit {sha} did not touch file {rel}")
    diff = run_git(resolved_root, ["show", sha, "--", rel], timeout_seconds)
    _check_quote(evidence, normalize_quote(diff))


def validate_evidence(
    root: Path,
    evidence: Evidence,
    timeout_seconds: float = _GIT_TIMEOUT_SECONDS,
) -> None:
    """Check one evidence item; raise ValidationError with the exact reason.

    Raises `SandboxViolationError` (a distinct type) when the cited path
    escapes the allowed root, so callers can distinguish attacks from bad
    citations.
    """
    if evidence.line_end < evidence.line_start:
        raise _fail(
            evidence,
            f"line_end {evidence.line_end} is before line_start {evidence.line_start}",
        )
    if evidence.kind in ("log", "source"):
        _validate_file_citation(root, evidence)
    else:
        _validate_commit_citation(root, evidence, timeout_seconds)
