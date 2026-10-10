"""Diagnosis schema submitted by the agent via the submit_diagnosis tool."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from regtriage.validation import Evidence


class SuspectedFile(BaseModel):
    """One file the agent suspects, with the reason in plain words."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    reason: str = ""


class Diagnosis(BaseModel):
    """Final per-cluster answer. `failed_evidence` lists every citation that
    did not validate, so rejected evidence is reported, never dropped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str = Field(min_length=1)
    root_cause_summary: str = Field(max_length=400)
    suspected_files: list[SuspectedFile] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    next_steps: list[str] = Field(default_factory=list, max_length=3)
    status: Literal["verified", "unverified", "failed"]
    failed_evidence: list[str] = Field(default_factory=list)
