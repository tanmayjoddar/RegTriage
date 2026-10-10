"""Read-only file tools: line-window log reads and source grep."""

import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from regtriage.errors import ParsingError, SandboxViolationError
from regtriage.tools.sandbox import (
    _DEFAULT_MAX_BYTES,
    _DEFAULT_MAX_LINES,
    _DEFAULT_MAX_RESULTS,
    _MAX_FILE_BYTES,
    resolve_within_root,
)

_MAX_PATTERN_LEN = 200
_MAX_FILES_SCANNED = 500
_MAX_FILE_SCAN_BYTES = 256_000
_MAX_MATCH_LINE_CHARS = 20_000
_MAX_HIT_TEXT_CHARS = 500
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules"})

# A quantified group that itself contains a quantifier or an alternation is
# the classic catastrophic-backtracking shape, e.g. (a+)+, (a*)*, (a|aa)+.
_NESTED_QUANTIFIER_RE = re.compile(r"\([^()]*[+*?][^()]*\)[+*?{]")
_QUANTIFIED_ALTERNATION_RE = re.compile(r"\([^()]*\|[^()]*\)[+*?{]")


class GrepHit(BaseModel):
    """One grep match: root-relative path, 1-based line number, line text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    text: str = ""


def read_log_lines(
    root: Path,
    path: str,
    start_line: int = 1,
    num_lines: int = 50,
    max_lines: int = _DEFAULT_MAX_LINES,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_file_bytes: int = _MAX_FILE_BYTES,
) -> list[str]:
    """Return `num_lines` of `path` from `start_line` as `N: content` strings.

    The file is streamed line by line, so only the requested window is
    decoded; huge files are refused by size before reading. Bytes and line
    counts are capped so one call cannot exhaust memory.
    """
    if start_line < 1 or num_lines < 1:
        raise SandboxViolationError(
            f"start_line and num_lines must be >= 1, got {start_line}/{num_lines}",
            attempted_target=path,
            violation_type="invalid_range",
        )
    if num_lines > max_lines:
        raise SandboxViolationError(
            f"num_lines {num_lines} exceeds the per-call cap {max_lines}",
            attempted_target=path,
            violation_type="resource_limit",
        )
    resolved = resolve_within_root(root, path)
    if not resolved.is_file():
        raise ParsingError(f"log file does not exist: {path}", source_path=path)
    if resolved.stat().st_size > max_file_bytes:
        raise SandboxViolationError(
            f"file larger than {max_file_bytes} bytes: {path}",
            attempted_target=path,
            violation_type="resource_limit",
        )
    out: list[str] = []
    used = 0
    with open(resolved, "rb") as handle:
        for lineno, raw in enumerate(handle, start=1):
            if lineno < start_line:
                continue
            if lineno >= start_line + num_lines:
                break
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            entry = f"{lineno}: {text}"
            if used + len(entry) > max_bytes:
                out.append(f"[output truncated at {max_bytes} bytes]")
                break
            out.append(entry)
            used += len(entry)
    return out


def _reject_catastrophic_pattern(pattern: str) -> None:
    """Statically reject regex shapes known for catastrophic backtracking."""
    if len(pattern) > _MAX_PATTERN_LEN:
        raise SandboxViolationError(
            f"pattern longer than {_MAX_PATTERN_LEN} chars",
            attempted_target=pattern[:100],
            violation_type="resource_limit",
        )
    if _NESTED_QUANTIFIER_RE.search(pattern) or _QUANTIFIED_ALTERNATION_RE.search(pattern):
        raise SandboxViolationError(
            f"pattern may backtrack catastrophically: {pattern[:100]}",
            attempted_target=pattern[:100],
            violation_type="catastrophic_pattern",
        )


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile an agent-supplied pattern, rejecting dangerous shapes first."""
    _reject_catastrophic_pattern(pattern)
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SandboxViolationError(
            f"invalid regex pattern: {exc}",
            attempted_target=pattern[:100],
            violation_type="invalid_pattern",
        ) from exc


def grep_source(
    root: Path,
    pattern: str,
    path_prefix: str | None = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> list[GrepHit]:
    """Search files under `root` (or `path_prefix`) for `pattern`, line by line.

    Directory symlinks are never followed, files outside the root are
    skipped, and binary or oversized files are skipped, so untrusted repo
    contents cannot pull the search elsewhere or blow memory.
    """
    if max_results < 1:
        raise SandboxViolationError(
            f"max_results must be >= 1, got {max_results}",
            violation_type="invalid_range",
        )
    compiled = _compile_pattern(pattern)
    base = resolve_within_root(root, path_prefix) if path_prefix is not None else None
    resolved_root = resolve_within_root(root, ".")
    start = base if base is not None else resolved_root
    if not start.is_dir():
        raise ParsingError(
            f"search base is not a directory: {path_prefix}", source_path=path_prefix
        )
    hits: list[GrepHit] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for name in sorted(filenames):
            if len(hits) >= max_results or scanned >= _MAX_FILES_SCANNED:
                return hits
            candidate = (Path(dirpath) / name).resolve()
            if candidate != resolved_root and resolved_root not in candidate.parents:
                continue
            if not candidate.is_file():
                continue
            if candidate.stat().st_size > _MAX_FILE_SCAN_BYTES:
                continue
            scanned += 1
            try:
                data = candidate.read_bytes()
            except OSError:
                continue
            if b"\0" in data[:8192]:
                continue
            for lineno, raw in enumerate(data.split(b"\n"), start=1):
                if len(hits) >= max_results:
                    return hits
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                window = text[:_MAX_MATCH_LINE_CHARS]
                if compiled.search(window) is None:
                    continue
                rel = candidate.relative_to(resolved_root).as_posix()
                hits.append(GrepHit(path=rel, line=lineno, text=text[:_MAX_HIT_TEXT_CHARS]))
    return hits
