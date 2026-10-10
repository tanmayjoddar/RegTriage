"""Process executors: local runs and Slurm batch submission."""

from regtriage.runner.executor import Executor, JobResult, JobSpec
from regtriage.runner.local import LocalExecutor
from regtriage.runner.slurm import SlurmExecutor, render_batch_script

__all__ = [
    "Executor",
    "JobResult",
    "JobSpec",
    "LocalExecutor",
    "SlurmExecutor",
    "render_batch_script",
]
