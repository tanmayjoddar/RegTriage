"""UVM log parser: UVM_ERROR / UVM_FATAL lines become Failures."""

import re
from pathlib import Path

from regtriage.errors import ConfigurationError
from regtriage.parsing.base import Failure
from regtriage.parsing.logs import DEFAULT_MAX_BYTES, DEFAULT_MAX_EXCERPT_CHARS, read_log_text

_UVM_RE = re.compile(r"UVM_(ERROR|FATAL)\b\s*(.*)")


class UvmLogParser:
    """Parse simulator logs for UVM_ERROR and UVM_FATAL report lines."""

    def __init__(
        self,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_excerpt_chars: int = DEFAULT_MAX_EXCERPT_CHARS,
    ) -> None:
        if max_bytes < 1:
            raise ConfigurationError(
                f"max_bytes must be at least 1, got {max_bytes}", parameter_name="max_bytes"
            )
        if max_excerpt_chars < 1:
            raise ConfigurationError(
                f"max_excerpt_chars must be at least 1, got {max_excerpt_chars}",
                parameter_name="max_excerpt_chars",
            )
        self._max_bytes = max_bytes
        self._max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> list[Failure]:
        """Return one Failure per UVM_ERROR/UVM_FATAL line, with line numbers."""
        lines = read_log_text(path, self._max_bytes)
        failures: list[Failure] = []
        for lineno, line in enumerate(lines, start=1):
            match = _UVM_RE.search(line)
            if match is None:
                continue
            kind, detail = match.group(1), match.group(2).strip()
            message = f"UVM_{kind} {detail}".strip()
            failures.append(
                Failure(
                    test=f"uvm_{kind.lower()}",
                    message=message[:2000],
                    log_path=path,
                    line=lineno,
                    raw_excerpt=line.strip()[: self._max_excerpt_chars],
                )
            )
        return failures
