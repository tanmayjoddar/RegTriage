"""Read-only git tools: blame and log over the allowed checkout."""

import os
import subprocess  # nosec B404: git inspection is the tool's job; argv lists only, never shell.
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from regtriage.errors import ExecutionError, SandboxViolationError
from regtriage.tools.sandbox import resolve_within_root

_GIT_TIMEOUT_SECONDS = 30.0
_DEFAULT_LOG_COUNT = 20
_MAX_LOG_COUNT = 100


class BlameLine(BaseModel):
    """One blamed line: 1-based number, commit sha, author, line content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    line: int = Field(ge=1)
    sha: str = Field(min_length=1)
    author: str = ""
    text: str = ""


class CommitInfo(BaseModel):
    """One commit: sha, author, short date, and subject line."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sha: str = Field(min_length=1)
    author: str = ""
    date: str = ""
    subject: str = ""


def _git_environ(root: Path) -> dict[str, str]:
    """Scrubbed environment for git children.

    No GIT_* variable passes through: GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE
    could redirect commands at a decoy repo (demonstrated: fatal "outside
    repository"), and GIT_CONFIG_* could inject aliases, diff drivers, or
    pager commands. The user global config is replaced by the null device
    and discovery may not ascend above the root.

    Two deliberate non-settings, both empirically grounded on Git-for-Windows:
    GIT_CONFIG_NOSYSTEM is NOT set, because the system config carries the
    line-ending conversion that blame needs to attribute correctly —
    disabling it alongside the global config collapses multi-commit blame
    to all-zero SHAs (reproduced; single-var and pair experiments recorded
    in the verification log). Conversion itself is NOT pinned either: our
    writes (prepare_case) and reads share this exact environment, so they
    always agree with each other, and reads match ambient-committed repos on
    both Windows (system autocrlf) and Linux (built-in default). Pinning
    conversion would reintroduce the same mismatch class against
    third-party checkouts. System config is image-level trusted surface,
    unlike environment variables. Everything else (PATH, SystemRoot,
    locale) is inherited unchanged.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CEILING_DIRECTORIES"] = str(root)
    return env


def _spawn(
    root: Path, args: list[str], timeout_seconds: float
) -> subprocess.CompletedProcess[bytes]:
    """Run git with byte pipes; map spawn/timeout failures to ExecutionError.

    Byte pipes matter: decoding happens in our thread, so undecodable output
    raises here instead of dying silently inside a subprocess reader thread.
    """
    argv = ["git", "-C", str(root)] + args
    try:
        return subprocess.run(  # nosec B603: argv list only, shell is never enabled.
            argv,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=_git_environ(root),
        )
    except FileNotFoundError as exc:
        raise ExecutionError("git executable not found on PATH", command=argv) from exc
    except subprocess.TimeoutExpired as exc:
        raise ExecutionError(
            f"git command timed out after {timeout_seconds}s",
            command=argv,
            timed_out=True,
        ) from exc


def _check_returncode(argv: list[str], completed: subprocess.CompletedProcess[bytes]) -> None:
    """Raise ExecutionError for nonzero exits (stderr decoded lossily)."""
    if completed.returncode != 0:
        raw_stderr = completed.stderr
        stderr = (
            raw_stderr.decode("utf-8", errors="replace").strip()[:500]
            if isinstance(raw_stderr, bytes)
            else ""
        )
        raise ExecutionError(
            f"git command failed: {stderr}",
            command=argv,
            returncode=completed.returncode,
            stderr=stderr,
        )


def run_git(
    root: Path,
    args: list[str],
    timeout_seconds: float,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> str:
    """Run one git argv list inside `root`; every call carries a timeout.

    Decoding is explicit UTF-8 (never locale-dependent) so output bytes mean
    the same on every platform; pass errors="strict" when undecodable output
    must raise instead of mojibake.
    """
    argv = ["git", "-C", str(root)] + args
    completed = _spawn(root, args, timeout_seconds)
    _check_returncode(argv, completed)
    raw = completed.stdout
    if not isinstance(raw, bytes):
        raise ExecutionError("git produced no output", command=argv)
    return raw.decode(encoding, errors)


def run_git_bytes(root: Path, args: list[str], timeout_seconds: float) -> bytes:
    """Run one git argv list and return raw stdout bytes for exact decoding."""
    argv = ["git", "-C", str(root)] + args
    completed = _spawn(root, args, timeout_seconds)
    _check_returncode(argv, completed)
    raw = completed.stdout
    if not isinstance(raw, bytes):
        raise ExecutionError("git produced no output", command=argv)
    return raw


def git_blame(
    root: Path,
    path: str,
    line_start: int,
    line_end: int,
    timeout_seconds: float = _GIT_TIMEOUT_SECONDS,
) -> list[BlameLine]:
    """Blame lines `line_start..line_end` of `path`; `path` stays in `root`."""
    if line_start < 1 or line_end < line_start:
        raise SandboxViolationError(
            f"invalid blame range {line_start}..{line_end}",
            attempted_target=path,
            violation_type="invalid_range",
        )
    resolved = resolve_within_root(root, path)
    out = run_git(
        resolve_within_root(root, "."),
        ["blame", "--porcelain", "-L", f"{line_start},{line_end}", "--", str(resolved)],
        timeout_seconds,
    )
    lines: list[BlameLine] = []
    sha = ""
    author = ""
    lineno = line_start
    # Porcelain omits the commit/author block for consecutive lines from the
    # same commit, so sha/author intentionally carry over between content lines.
    for raw in out.splitlines():
        if raw.startswith("author "):
            author = raw[len("author ") :]
        elif len(raw) >= 41 and raw[40] == " " and all(c in "0123456789abcdef" for c in raw[:40]):
            sha = raw[:40]
        elif raw.startswith("\t"):
            lines.append(BlameLine(line=lineno, sha=sha, author=author, text=raw[1:]))
            lineno += 1
    return lines


def git_log(
    root: Path,
    path: str | None = None,
    max_count: int = _DEFAULT_LOG_COUNT,
    timeout_seconds: float = _GIT_TIMEOUT_SECONDS,
) -> list[CommitInfo]:
    """List recent commits (optionally touching `path`); newest first."""
    if max_count < 1 or max_count > _MAX_LOG_COUNT:
        raise SandboxViolationError(
            f"max_count must be 1..{_MAX_LOG_COUNT}, got {max_count}",
            violation_type="invalid_range",
        )
    resolved_root = resolve_within_root(root, ".")
    args = [
        "log",
        "--format=%H%x00%an%x00%ad%x00%s%x1e",
        "--date=short",
        "-n",
        str(max_count),
    ]
    if path is not None:
        resolved = resolve_within_root(root, path)
        args += ["--", str(resolved)]
    out = run_git(resolved_root, args, timeout_seconds)
    commits: list[CommitInfo] = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x00")
        if len(parts) != 4:
            continue
        commits.append(CommitInfo(sha=parts[0], author=parts[1], date=parts[2], subject=parts[3]))
    return commits
