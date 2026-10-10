"""Local process executor with bounded parallelism and per-job timeouts."""

import os
import signal
import subprocess  # nosec B404: process spawning is the executor's job; argv lists only, never shell.
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from regtriage.errors import ConfigurationError, ExecutionError
from regtriage.runner.executor import JobResult, JobSpec

_DEFAULT_TIMEOUT_SECONDS = 120.0
_MAX_OUTPUT_CHARS = 200_000
# POSIX kill signal number. Windows has no signal.SIGKILL, and the killpg
# branch below only runs when os.name == "posix", so fall back to 9 there.
_SIGKILL: int = getattr(signal, "SIGKILL", 9)


def _tail(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Keep the last `limit` characters so long simulator logs fit in memory."""
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return f"[truncated {dropped} leading chars]\n" + text[-limit:]


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    """Kill the whole process group on POSIX so grandchildren die on timeout."""
    if os.name == "posix":
        killpg = getattr(os, "killpg", None)
        if killpg is not None:
            try:
                killpg(proc.pid, _SIGKILL)
                return
            except OSError:
                pass
    proc.kill()


def run_one_job(spec: JobSpec, default_timeout_seconds: float) -> JobResult:
    """Run one argv list to completion, killing its process group on timeout."""
    timeout = spec.timeout_seconds
    if timeout is None:
        timeout = default_timeout_seconds
    if timeout <= 0:
        raise ConfigurationError(
            "timeout_seconds must be positive",
            parameter_name="timeout_seconds",
        )
    cwd = str(spec.cwd) if spec.cwd is not None else None
    try:
        proc = subprocess.Popen(  # nosec B603: argv list only, shell is never enabled.
            spec.argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        raise ExecutionError(
            f"failed to start job {spec.job_id}: {exc}",
            command=spec.argv,
        ) from exc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        stdout, stderr = proc.communicate()
        code = proc.returncode
        if code is None:  # Unreachable after communicate(); narrows the type.
            code = -1
        return JobResult(
            job_id=spec.job_id,
            returncode=code,
            stdout=_tail(stdout),
            stderr=_tail(stderr),
            timed_out=True,
        )
    code = proc.returncode
    if code is None:  # Unreachable after communicate(); narrows the type.
        code = -1
    return JobResult(
        job_id=spec.job_id,
        returncode=code,
        stdout=_tail(stdout),
        stderr=_tail(stderr),
        timed_out=False,
    )


class LocalExecutor:
    """Run jobs as local processes with at most `max_parallel` at once."""

    def __init__(
        self,
        max_parallel: int = 4,
        default_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if max_parallel < 1:
            raise ConfigurationError(
                f"max_parallel must be at least 1, got {max_parallel}",
                parameter_name="max_parallel",
            )
        if default_timeout_seconds <= 0:
            raise ConfigurationError(
                "default_timeout_seconds must be positive",
                parameter_name="default_timeout_seconds",
            )
        self._max_parallel = max_parallel
        self._default_timeout_seconds = default_timeout_seconds

    def run_jobs(self, specs: list[JobSpec]) -> list[JobResult]:
        """Run every spec, preserving input order in the output list."""
        run = partial(run_one_job, default_timeout_seconds=self._default_timeout_seconds)
        with ThreadPoolExecutor(max_workers=self._max_parallel) as pool:
            return list(pool.map(run, specs))
