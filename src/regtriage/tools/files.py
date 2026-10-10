"""Read-only file tools: line-window log reads and source grep."""

import json
import os
import subprocess  # nosec B404: regex worker spawn is the tool's job; argv lists only, never shell.
import sys
from collections.abc import Generator
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from regtriage.errors import ExecutionError, ParsingError, SandboxViolationError
from regtriage.tools.sandbox import (
    _DEFAULT_MAX_BYTES,
    _DEFAULT_MAX_LINES,
    _DEFAULT_MAX_RESULTS,
    _MAX_FILE_BYTES,
    denied_name_reason,
    resolve_within_root,
)

_MAX_PATTERN_LEN = 200
_MAX_FILES_SCANNED = 500
_MAX_FILE_SCAN_BYTES = 256_000
_MAX_MATCH_LINE_CHARS = 20_000
_MAX_HIT_TEXT_CHARS = 500
_CHILD_HIT_CAP = 2000
_DEFAULT_REGEX_TIMEOUT_SECONDS = 5.0
_MAX_REGEX_TIMEOUT_SECONDS = 5.0
_MAX_TOTAL_SCAN_BYTES = 2_000_000
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules"})

# Regex matching runs in a sacrificial child process (never the agent host),
# so a catastrophic pattern burns child CPU until the parent kills it. The
# child is plain stdlib with no imports beyond json/re/sys.
_CHILD_SOURCE = """\
import json
import re
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        pattern = str(payload["pattern"])
        files = list(payload["files"])
        line_cap = int(payload.get("line_cap", 20000))
        hit_cap = int(payload.get("hit_cap", 2000))
    except Exception as exc:
        sys.stderr.write("bad worker input: " + str(exc) + "\\n")
        return 3
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        sys.stderr.write("invalid regex: " + str(exc) + "\\n")
        return 2
    hits = []
    for index, lines in enumerate(files):
        for lineno, text in enumerate(lines, start=1):
            window = str(text)[:line_cap]
            try:
                matched = compiled.search(window) is not None
            except Exception:
                continue
            if matched:
                hits.append({"i": index, "line": lineno, "text": str(text)[:500]})
                if len(hits) >= hit_cap:
                    sys.stdout.write(json.dumps({"hits": hits, "truncated": True}))
                    return 0
    sys.stdout.write(json.dumps({"hits": hits, "truncated": False}))
    return 0


sys.exit(main())
"""


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


def _check_pattern(pattern: str, regex_timeout_seconds: float) -> None:
    """Enforce resource caps on the pattern; shape sniffing is gone.

    Length is bounded, but any shape is accepted: literal search cannot
    backtrack, and regex runs in a killable child process.
    """
    if not pattern:
        raise SandboxViolationError(
            "pattern must not be empty",
            attempted_target=pattern,
            violation_type="invalid_pattern",
        )
    if len(pattern) > _MAX_PATTERN_LEN:
        raise SandboxViolationError(
            f"pattern longer than {_MAX_PATTERN_LEN} chars",
            attempted_target=pattern[:100],
            violation_type="resource_limit",
        )
    if regex_timeout_seconds <= 0:
        raise SandboxViolationError(
            f"regex_timeout_seconds must be positive, got {regex_timeout_seconds}",
            violation_type="invalid_range",
        )


def _iter_candidates(start: Path, resolved_root: Path) -> Generator[tuple[str, list[str]], None, None]:
    """Yield (relpath, lines) per readable file under `start`.

    Same skips as before: pruned dirs, outside symlinks, denied names,
    non-files, oversized and binary files. Bounded by _MAX_FILES_SCANNED
    AND _MAX_TOTAL_SCAN_BYTES, so one grep call can never buffer the whole
    corpus for the regex child: at most ~2 MB of file bytes go over stdin.
    """
    scanned = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for name in sorted(filenames):
            if scanned >= _MAX_FILES_SCANNED or total_bytes >= _MAX_TOTAL_SCAN_BYTES:
                return
            candidate = (Path(dirpath) / name).resolve()
            if candidate != resolved_root and resolved_root not in candidate.parents:
                continue
            if denied_name_reason(candidate) is not None:
                continue
            if not candidate.is_file():
                continue
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_SCAN_BYTES:
                continue
            if total_bytes + size > _MAX_TOTAL_SCAN_BYTES:
                return
            scanned += 1
            try:
                data = candidate.read_bytes()
            except OSError:
                continue
            if b"\0" in data[:8192]:
                continue
            total_bytes += len(data)
            rel = candidate.relative_to(resolved_root).as_posix()
            lines = [
                raw.decode("utf-8", errors="replace").rstrip("\r\n") for raw in data.split(b"\n")
            ]
            yield (rel, lines)


def _collect_candidates(start: Path, resolved_root: Path) -> list[tuple[str, list[str]]]:
    """Walk files under `start`, returning (relpath, lines) per readable file.

    Bounded collector over _iter_candidates; the fixed-string path streams
    instead so it can stop early at the hit cap.
    """
    return list(_iter_candidates(start, resolved_root))


def _run_regex_worker(
    pattern: str,
    candidates: list[tuple[str, list[str]]],
    timeout_seconds: float,
    hit_cap: int = _CHILD_HIT_CAP,
) -> list[GrepHit]:
    """Match one regex in a sacrificial child killed on timeout.

    The child receives file lines over stdin and returns JSON hits on
    stdout. `hit_cap` bounds the child's output (callers pass max_results);
    catastrophic patterns die by the clock.
    """
    hit_cap = max(1, min(hit_cap, _CHILD_HIT_CAP))
    payload = json.dumps(
        {
            "pattern": pattern,
            "files": [lines for _, lines in candidates],
            "line_cap": _MAX_MATCH_LINE_CHARS,
            "hit_cap": hit_cap,
        }
    )
    try:
        proc = subprocess.Popen(  # nosec B603: argv list only, shell is never enabled.
            [sys.executable, "-c", _CHILD_SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise ExecutionError(
            f"cannot start regex worker: {exc}",
            command=[sys.executable, "-c", "<regex worker>"],
        ) from exc
    try:
        stdout, stderr = proc.communicate(payload, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise SandboxViolationError(
            f"regex search timed out after {timeout_seconds}s",
            attempted_target=pattern[:100],
            violation_type="regex_timeout",
        ) from exc
    if proc.returncode == 2:
        raise SandboxViolationError(
            f"invalid regex pattern: {stderr.strip()[:200]}",
            attempted_target=pattern[:100],
            violation_type="invalid_pattern",
        )
    if proc.returncode != 0:
        raise ExecutionError(
            f"regex worker failed with exit {proc.returncode}: {stderr.strip()[:200]}",
            command=[sys.executable, "-c", "<regex worker>"],
            returncode=proc.returncode,
            stderr=stderr.strip()[:200],
        )
    try:
        data = json.loads(stdout)
        raw_hits = data["hits"]
        assert isinstance(raw_hits, list)
    except (ValueError, KeyError, TypeError, AssertionError) as exc:
        raise ExecutionError("regex worker returned malformed output") from exc
    hits: list[GrepHit] = []
    rels = [rel for rel, _ in candidates]
    for entry in raw_hits:
        try:
            assert isinstance(entry, dict)
            index = int(entry["i"])
            lineno = int(entry["line"])
            text = str(entry["text"])
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            raise ExecutionError("regex worker returned a malformed hit") from exc
        if not 0 <= index < len(rels) or lineno < 1:
            raise ExecutionError("regex worker returned an out-of-range hit")
        hits.append(GrepHit(path=rels[index], line=lineno, text=text[:_MAX_HIT_TEXT_CHARS]))
    return hits


def grep_source(
    root: Path,
    pattern: str,
    path_prefix: str | None = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
    fixed_strings: bool = True,
    regex_timeout_seconds: float = _DEFAULT_REGEX_TIMEOUT_SECONDS,
) -> list[GrepHit]:
    """Search files under `root` (or `path_prefix`) for `pattern`, line by line.

    By default the pattern is a fixed string: no regex is ever compiled, so
    catastrophic backtracking is impossible by construction. Pass
    `fixed_strings=False` to opt into regex, which compiles and matches in a
    sacrificial child process killed after `regex_timeout_seconds`.
    Directory symlinks are never followed, files outside the root are
    skipped, and binary or oversized files are skipped.
    """
    if max_results < 1:
        raise SandboxViolationError(
            f"max_results must be >= 1, got {max_results}",
            violation_type="invalid_range",
        )
    _check_pattern(pattern, regex_timeout_seconds)
    # Internal callers only: clamp any explicit timeout to the server max.
    timeout_seconds = min(regex_timeout_seconds, _MAX_REGEX_TIMEOUT_SECONDS)
    base = resolve_within_root(root, path_prefix) if path_prefix is not None else None
    resolved_root = resolve_within_root(root, ".")
    start = base if base is not None else resolved_root
    if not start.is_dir():
        raise ParsingError(
            f"search base is not a directory: {path_prefix}", source_path=path_prefix
        )
    if fixed_strings:
        hits: list[GrepHit] = []
        # Stream file by file and stop at the cap: files past the cap are
        # never even read (early exit).
        for rel, lines in _iter_candidates(start, resolved_root):
            for lineno, text in enumerate(lines, start=1):
                if len(hits) >= max_results:
                    return hits
                if pattern in text[:_MAX_MATCH_LINE_CHARS]:
                    hits.append(GrepHit(path=rel, line=lineno, text=text[:_MAX_HIT_TEXT_CHARS]))
        return hits
    candidates = _collect_candidates(start, resolved_root)
    return _run_regex_worker(pattern, candidates, timeout_seconds, hit_cap=max_results)[:max_results]
