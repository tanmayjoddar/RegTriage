"""Parser Protocol and the Failure record shared by all log parsers."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class Failure(BaseModel):
    """One failed check: which test, what it said, where the evidence lives."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    test: str = Field(min_length=1)
    message: str = ""
    log_path: Path | None = None
    line: int | None = None
    raw_excerpt: str = ""


class Parser(Protocol):
    """Reads one artifact file and returns every failure found in it."""

    def parse(self, path: Path) -> list[Failure]:
        """Return failures in `path`, or raise ParsingError if unreadable."""
        ...
