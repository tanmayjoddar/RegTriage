"""Process executors: local runs now, Slurm arrives in Slice 9."""

from regtriage.runner.executor import Executor, JobResult, JobSpec
from regtriage.runner.local import LocalExecutor

__all__ = ["Executor", "JobResult", "JobSpec", "LocalExecutor"]
