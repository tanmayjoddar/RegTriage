"""Executor Protocol and job models shared by Local and Slurm executors."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class JobSpec(BaseModel):
    """One command to run: an argv list, an optional cwd, an optional timeout."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    argv: list[str] = Field(min_length=1)
    cwd: Path | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class JobResult(BaseModel):
    """What happened when a job ran: exit code, captured output, timeout flag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class Executor(Protocol):
    """Runs a batch of JobSpecs and returns one JobResult per spec, in order."""

    def run_jobs(self, specs: list[JobSpec]) -> list[JobResult]:
        """Run every spec and return results in the same order."""
        ...
