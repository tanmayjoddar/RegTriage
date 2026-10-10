"""Unit tests for LocalExecutor (real subprocesses, no mocks)."""

import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from regtriage.errors import ConfigurationError, ExecutionError
from regtriage.runner import JobSpec, LocalExecutor


def _python_job(job_id: str, code: str, timeout: float | None = None) -> JobSpec:
    """Build a JobSpec that runs `code` with the current Python interpreter."""
    return JobSpec(job_id=job_id, argv=[sys.executable, "-c", code], timeout_seconds=timeout)


def test_single_job_captures_stdout_and_stderr() -> None:
    executor = LocalExecutor(max_parallel=2)
    spec = _python_job("echo", "print('hello-sim')")
    (result,) = executor.run_jobs([spec])
    assert result.job_id == "echo"
    assert result.returncode == 0
    assert result.stdout == "hello-sim\n"
    assert result.timed_out is False


def test_stderr_is_captured_separately() -> None:
    executor = LocalExecutor(max_parallel=1)
    spec = _python_job("warn", "import sys; sys.stderr.write('sim warning\\n')")
    (result,) = executor.run_jobs([spec])
    assert result.returncode == 0
    assert result.stderr == "sim warning\n"
    assert result.stdout == ""


def test_nonzero_exit_reports_returncode_without_timeout() -> None:
    executor = LocalExecutor(max_parallel=1)
    spec = _python_job("fail", "import sys; sys.exit(3)")
    (result,) = executor.run_jobs([spec])
    assert result.returncode == 3
    assert result.timed_out is False


def test_timeout_kills_job_and_flags_timed_out() -> None:
    executor = LocalExecutor(max_parallel=1, default_timeout_seconds=60.0)
    spec = _python_job("hang", "import time; time.sleep(60)", timeout=1.0)
    started = time.monotonic()
    (result,) = executor.run_jobs([spec])
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert elapsed < 30.0


def test_job_uses_executor_default_timeout() -> None:
    executor = LocalExecutor(max_parallel=1, default_timeout_seconds=1.0)
    spec = _python_job("hang-default", "import time; time.sleep(60)")
    (result,) = executor.run_jobs([spec])
    assert result.timed_out is True


def test_missing_binary_raises_execution_error() -> None:
    executor = LocalExecutor(max_parallel=1)
    spec = JobSpec(job_id="ghost", argv=["definitely-not-a-real-binary-xyz"])
    with pytest.raises(ExecutionError) as exc_info:
        executor.run_jobs([spec])
    assert exc_info.value.command == ["definitely-not-a-real-binary-xyz"]


def test_invalid_constructor_args_rejected() -> None:
    with pytest.raises(ConfigurationError):
        LocalExecutor(max_parallel=0)
    with pytest.raises(ConfigurationError):
        LocalExecutor(max_parallel=2, default_timeout_seconds=0.0)


def test_invalid_spec_rejected_by_validation() -> None:
    with pytest.raises(PydanticValidationError):
        JobSpec(job_id="", argv=[sys.executable])
    with pytest.raises(PydanticValidationError):
        JobSpec(job_id="empty-argv", argv=[])
    with pytest.raises(PydanticValidationError):
        JobSpec(job_id="bad-timeout", argv=[sys.executable], timeout_seconds=0.0)


def test_results_preserve_input_order() -> None:
    executor = LocalExecutor(max_parallel=3)
    specs = [
        _python_job("slow", "import time; time.sleep(0.5); print('slow')"),
        _python_job("fast-a", "print('a')"),
        _python_job("fast-b", "print('b')"),
    ]
    results = executor.run_jobs(specs)
    assert [r.job_id for r in results] == ["slow", "fast-a", "fast-b"]
    assert [r.stdout for r in results] == ["slow\n", "a\n", "b\n"]
    assert all(r.returncode == 0 for r in results)


def test_serial_executor_runs_jobs_one_at_a_time() -> None:
    executor = LocalExecutor(max_parallel=1)
    specs = [
        _python_job("one", "import time; time.sleep(0.5)"),
        _python_job("two", "import time; time.sleep(0.5)"),
    ]
    started = time.monotonic()
    results = executor.run_jobs(specs)
    elapsed = time.monotonic() - started
    assert all(r.returncode == 0 for r in results)
    assert elapsed >= 0.9


def test_large_output_is_truncated_to_bound_memory() -> None:
    executor = LocalExecutor(max_parallel=1)
    spec = _python_job("noisy", "print('x' * 300000)")
    (result,) = executor.run_jobs([spec])
    assert result.returncode == 0
    assert "truncated" in result.stdout
    assert len(result.stdout) <= 200_100


def test_job_runs_in_given_cwd(tmp_path: Path) -> None:
    workdir = tmp_path / "sim"
    workdir.mkdir()
    executor = LocalExecutor(max_parallel=1)
    spec = JobSpec(
        job_id="pwd",
        argv=[sys.executable, "-c", "import pathlib; print(pathlib.Path.cwd().name)"],
        cwd=workdir,
    )
    (result,) = executor.run_jobs([spec])
    assert result.returncode == 0
    assert result.stdout.strip() == "sim"
