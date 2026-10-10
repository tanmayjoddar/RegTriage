"""SlurmExecutor tests against fake sbatch/squeue/sacct/scancel shims on PATH.

Shim tests need POSIX exec permission and skip elsewhere with a reason;
template, constructor, and missing-binary tests run everywhere.
"""

import os
import shutil
import stat
from pathlib import Path

import pytest

from regtriage.errors import ConfigurationError, ExecutionError
from regtriage.runner import JobSpec, SlurmExecutor
from regtriage.runner.slurm import render_batch_script

SBATCH_SH = """#!/bin/sh
echo "sbatch $@" >> "$SHIM_LOG/calls.log"
if [ -n "$SHIM_SBATCH_FAIL" ]; then echo "submit failed" >&2; exit 1; fi
script=""
for arg in "$@"; do script="$arg"; done
out=$(grep '^#SBATCH --output=' "$script" | cut -d= -f2-)
err=$(grep '^#SBATCH --error=' "$script" | cut -d= -f2-)
cmd=$(grep -v '^#' "$script" | grep -v '^$' | tail -n 1)
sh -c "$cmd" >"$out" 2>"$err" &
echo 42
"""

SACCT_SH = """#!/bin/sh
echo "sacct $@" >> "$SHIM_LOG/calls.log"
if [ -n "$SHIM_SACCT_FAIL" ]; then exit 1; fi
if [ -n "$SHIM_NEVER_DONE" ]; then echo "PENDING"; exit 0; fi
n=$(cat "$SHIM_STATE/count" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$SHIM_STATE/count"
if [ "$n" -ge 3 ]; then echo "COMPLETED"; else echo "PENDING"; fi
"""

SQUEUE_SH = """#!/bin/sh
echo "squeue $@" >> "$SHIM_LOG/calls.log"
if [ -n "$SHIM_SQUEUE_HIT" ]; then echo "  42 debug jobname R 0:01 1 node"; fi
exit 0
"""

SCANCEL_SH = """#!/bin/sh
echo "scancel $@" >> "$SHIM_LOG/calls.log"
exit 0
"""


@pytest.fixture
def shim_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fake Slurm CLI on PATH; skips where scripts cannot execute."""
    if os.name != "posix":
        pytest.skip("slurm shims need POSIX exec permission")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (
        ("sbatch", SBATCH_SH),
        ("sacct", SACCT_SH),
        ("squeue", SQUEUE_SH),
        ("scancel", SCANCEL_SH),
    ):
        script = bindir / name
        script.write_text(body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logdir = tmp_path / "shimlog"
    logdir.mkdir()
    statedir = tmp_path / "shimstate"
    statedir.mkdir()
    (statedir / "count").write_text("0", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("SHIM_LOG", str(logdir))
    monkeypatch.setenv("SHIM_STATE", str(statedir))
    for key in ("SHIM_SBATCH_FAIL", "SHIM_SACCT_FAIL", "SHIM_NEVER_DONE", "SHIM_SQUEUE_HIT"):
        monkeypatch.delenv(key, raising=False)
    return bindir


def _calls(tmp_path: Path) -> str:
    log = tmp_path / "shimlog" / "calls.log"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


def test_render_batch_script_contains_directives(tmp_path: Path) -> None:
    script = render_batch_script(
        "job-1", ["echo", "sim-ok"], tmp_path / "o.txt", tmp_path / "e.txt"
    )
    assert "#SBATCH --job-name=job-1" in script
    assert f"#SBATCH --output={tmp_path / 'o.txt'}" in script
    assert script.strip().splitlines()[-1] == "echo sim-ok"
    quoted = render_batch_script("j", ["printf", "%s", "a b"], tmp_path / "o", tmp_path / "e")
    assert "a b" in quoted.splitlines()[-1]


def test_invalid_executor_args_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        SlurmExecutor(tmp_path, default_timeout_seconds=0)
    with pytest.raises(ConfigurationError):
        SlurmExecutor(tmp_path, poll_seconds=0)


def test_missing_slurm_binary_is_execution_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "emptybin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    with pytest.raises(ExecutionError):
        executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"])])


def test_happy_path_collects_output(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    (result,) = executor.run_jobs([JobSpec(job_id="sim", argv=["echo", "sim-ok"])])
    assert result.job_id == "sim"
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stdout.strip() == "sim-ok"
    assert "sbatch" in _calls(tmp_path) and "sacct" in _calls(tmp_path)


def test_submit_failure_raises(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIM_SBATCH_FAIL", "1")
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    with pytest.raises(ExecutionError):
        executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"])])


def test_timeout_cancels_and_flags(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIM_NEVER_DONE", "1")
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    (result,) = executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"], timeout_seconds=0.3)])
    assert result.timed_out is True
    assert "scancel 42" in _calls(tmp_path)


def test_failed_state_maps_to_nonzero(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    statedir = tmp_path / "shimstate"
    (statedir / "count").write_text("99", encoding="utf-8")
    sacct = shim_path / "sacct"
    sacct.write_text(
        '#!/bin/sh\necho "sacct $@" >> "$SHIM_LOG/calls.log"\necho "FAILED"\n',
        encoding="utf-8",
    )
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    (result,) = executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"])])
    assert result.returncode == 1
    assert result.timed_out is False


def test_unknown_state_maps_to_nonzero(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIM_SACCT_FAIL", "1")
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    (result,) = executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"])])
    assert result.returncode == 1


def test_squeue_pending_then_timeout(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIM_SACCT_FAIL", "1")
    monkeypatch.setenv("SHIM_SQUEUE_HIT", "1")
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    (result,) = executor.run_jobs([JobSpec(job_id="j", argv=["echo", "hi"], timeout_seconds=0.3)])
    assert result.timed_out is True


def test_run_jobs_preserves_order(
    tmp_path: Path, shim_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = SlurmExecutor(tmp_path / "work", poll_seconds=0.01)
    results = executor.run_jobs(
        [JobSpec(job_id="a", argv=["echo", "1"]), JobSpec(job_id="b", argv=["echo", "2"])]
    )
    assert [r.job_id for r in results] == ["a", "b"]
    assert shutil.which("sbatch") is not None
