"""Slurm executor: sbatch --parsable, sacct/squeue polling, scancel on timeout.

Batch scripts are rendered from an inline template (mirrored by the deploy/
template): SBATCH directives capture stdout/stderr to files, then the job's
argv runs. All Slurm commands use argv lists with a timeout; no shell.
"""

import contextlib
import shlex
import subprocess  # nosec B404: Slurm CLI calls are the executor's job; argv lists only, never shell.
import time
from pathlib import Path

from regtriage.errors import ConfigurationError, ExecutionError
from regtriage.runner.executor import JobResult, JobSpec

_DEFAULT_POLL_SECONDS = 10.0
_DEFAULT_TIMEOUT_SECONDS = 120.0
_MAX_OUTPUT_CHARS = 200_000

_BATCH_TEMPLATE = """#!/bin/bash
#SBATCH --job-name={job_id}
#SBATCH --output={stdout_path}
#SBATCH --error={stderr_path}
#SBATCH --time={time_limit}
#SBATCH --parsable

{command}
"""


def _tail(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Keep the last `limit` characters of captured output."""
    if len(text) <= limit:
        return text
    return f"[truncated {len(text) - limit} leading chars]\n" + text[-limit:]


def _run_slurm(
    argv: list[str], timeout_seconds: float, label: str
) -> subprocess.CompletedProcess[str]:
    """Run one Slurm CLI command; every call carries a timeout."""
    try:
        return subprocess.run(  # nosec B603: argv list only, shell is never enabled.
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ExecutionError(f"slurm command not found: {label}", command=argv) from exc
    except subprocess.TimeoutExpired as exc:
        raise ExecutionError(
            f"slurm command timed out: {label}", command=argv, timed_out=True
        ) from exc


def render_batch_script(
    job_id: str, argv: list[str], stdout_path: Path, stderr_path: Path, time_limit: str = "01:00:00"
) -> str:
    """Render the sbatch script for one job from the template."""
    return _BATCH_TEMPLATE.format(
        job_id=job_id,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        time_limit=time_limit,
        command=shlex.join(argv),
    )


class SlurmExecutor:
    """Submit jobs via sbatch and poll to completion (satisfies Executor)."""

    def __init__(
        self,
        work_dir: Path,
        default_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        poll_seconds: float = _DEFAULT_POLL_SECONDS,
        cli_timeout_seconds: float = 30.0,
    ) -> None:
        if default_timeout_seconds <= 0:
            raise ConfigurationError(
                "default_timeout_seconds must be positive",
                parameter_name="default_timeout_seconds",
            )
        if poll_seconds <= 0:
            raise ConfigurationError("poll_seconds must be positive", parameter_name="poll_seconds")
        self._work_dir = work_dir.expanduser().resolve()
        self._default_timeout_seconds = default_timeout_seconds
        self._poll_seconds = poll_seconds
        self._cli_timeout_seconds = cli_timeout_seconds

    def _submit(self, script_path: Path) -> str:
        """Submit one script with --parsable; return the job id."""
        completed = _run_slurm(
            ["sbatch", "--parsable", str(script_path)], self._cli_timeout_seconds, "sbatch"
        )
        if completed.returncode != 0:
            raise ExecutionError(
                f"sbatch failed: {completed.stderr.strip()[:500]}",
                command=["sbatch", str(script_path)],
                returncode=completed.returncode,
                stderr=completed.stderr.strip()[:500],
            )
        job_id = completed.stdout.strip().split(";")[0].strip()
        if not job_id:
            raise ExecutionError("sbatch returned no job id", command=["sbatch"])
        return job_id

    def _state(self, job_id: str) -> str:
        """Return the current sacct state, or UNKNOWN when squeue says gone."""
        completed = _run_slurm(
            ["sacct", "-j", job_id, "--format=State", "--noheader", "--parsable2"],
            self._cli_timeout_seconds,
            "sacct",
        )
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                state = line.strip().split("|")[0].strip()
                if state:
                    return state.upper()
        queued = _run_slurm(
            ["squeue", "-j", job_id, "--noheader"], self._cli_timeout_seconds, "squeue"
        )
        if queued.returncode == 0 and job_id in queued.stdout:
            return "PENDING"
        return "UNKNOWN"

    def _cancel(self, job_id: str) -> None:
        """Best-effort scancel; failures are swallowed (timeout path)."""
        with contextlib.suppress(ExecutionError):
            _run_slurm(["scancel", job_id], self._cli_timeout_seconds, "scancel")

    def _run_one(self, spec: JobSpec) -> JobResult:
        """Submit, poll until done, collect output files, enforce the timeout."""
        timeout = spec.timeout_seconds
        if timeout is None:
            timeout = self._default_timeout_seconds
        if timeout <= 0:
            raise ConfigurationError(
                "timeout_seconds must be positive", parameter_name="timeout_seconds"
            )
        job_dir = self._work_dir / spec.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = job_dir / "stdout.txt"
        stderr_path = job_dir / "stderr.txt"
        script_path = job_dir / "job.sbatch"
        script_path.write_text(
            render_batch_script(spec.job_id, spec.argv, stdout_path, stderr_path),
            encoding="utf-8",
        )
        job_id = self._submit(script_path)
        deadline = time.monotonic() + timeout
        state = self._state(job_id)
        while state not in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY"):
            if time.monotonic() >= deadline:
                self._cancel(job_id)
                return JobResult(
                    job_id=spec.job_id, returncode=-1, stdout="", stderr="", timed_out=True
                )
            if state == "UNKNOWN":
                break
            time.sleep(self._poll_seconds)
            state = self._state(job_id)
        try:
            stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stdout = ""
        try:
            stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stderr = ""
        code = 0 if state == "COMPLETED" else 1
        return JobResult(
            job_id=spec.job_id,
            returncode=code,
            stdout=_tail(stdout),
            stderr=_tail(stderr),
            timed_out=state == "TIMEOUT",
        )

    def run_jobs(self, specs: list[JobSpec]) -> list[JobResult]:
        """Submit jobs one at a time; Slurm itself schedules in parallel."""
        return [self._run_one(spec) for spec in specs]
