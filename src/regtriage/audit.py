"""Append-only JSONL audit log of every LLM request and response.

Payloads are the exact redacted-as-sent dictionaries, so the log never holds
live secrets. The file is created with mode 0600 when the platform supports
POSIX modes.
"""

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


class AuditLogger:
    """Append JSONL records; each write opens, appends, and closes."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser()

    @property
    def path(self) -> Path:
        """Return the configured log path."""
        return self._path

    def append(self, kind: Literal["request", "response"], payload: dict[str, Any]) -> None:
        """Append one record with a UTC timestamp; enforce owner-only mode."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "kind": kind,
            "payload": payload,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.chmod(self._path, 0o600)
