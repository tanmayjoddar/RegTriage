"""Evidence model for machine-checked agent citations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceKind = Literal["log", "source", "commit"]


class Evidence(BaseModel):
    """One cited fact: kind, reference, line window, and short quote.

    For `log`/`source`, `ref` is a repo-relative path and the window refers
    to file lines. For `commit`, `ref` is `<sha>:<repo-relative-path>` and
    the window refers to blob lines of that path at that commit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EvidenceKind
    ref: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str = Field(max_length=200)
