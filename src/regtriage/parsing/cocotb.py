"""JUnit results.xml parser for cocotb regressions."""

import xml.etree.ElementTree as ET  # nosec B405: stdlib parser; DOCTYPE rejected below, defusedxml not in allowed deps.
from pathlib import Path

from regtriage.errors import ConfigurationError, ParsingError
from regtriage.parsing.base import Failure

_MAX_MESSAGE_CHARS = 2000


class CocotbResultsParser:
    """Parses cocotb results.xml (JUnit format) into Failure records."""

    def __init__(
        self,
        max_bytes: int = 32_000_000,
        max_excerpt_chars: int = 4000,
    ) -> None:
        if max_bytes < 1:
            raise ConfigurationError(
                f"max_bytes must be at least 1, got {max_bytes}",
                parameter_name="max_bytes",
            )
        if max_excerpt_chars < 1:
            raise ConfigurationError(
                f"max_excerpt_chars must be at least 1, got {max_excerpt_chars}",
                parameter_name="max_excerpt_chars",
            )
        self._max_bytes = max_bytes
        self._max_excerpt_chars = max_excerpt_chars

    def parse(self, path: Path) -> list[Failure]:
        """Return one Failure per testcase containing a failure/error child."""
        if not path.is_file():
            raise ParsingError(
                f"results file does not exist: {path}",
                source_path=str(path),
            )
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ParsingError(
                f"cannot read results file: {path}",
                source_path=str(path),
            ) from exc
        if len(raw) > self._max_bytes:
            raise ParsingError(
                f"results file larger than {self._max_bytes} bytes: {path}",
                source_path=str(path),
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParsingError(
                f"results file is not valid UTF-8: {path}",
                source_path=str(path),
            ) from exc
        if "<!doctype" in text.lower():
            raise ParsingError(
                f"results file contains a DOCTYPE declaration, rejected: {path}",
                source_path=str(path),
            )
        try:
            root = ET.fromstring(text)  # nosec B314: DOCTYPE rejected above, so entity expansion is impossible.
        except ET.ParseError as exc:
            raise ParsingError(
                f"results file is not well-formed XML: {path}",
                source_path=str(path),
            ) from exc
        failures: list[Failure] = []
        for case in root.iter("testcase"):
            name = case.get("name") or "unknown"
            classname = case.get("classname") or ""
            test = f"{classname}::{name}" if classname else name
            for result in case:
                if result.tag not in ("failure", "error"):
                    continue
                message = (result.get("message") or "").strip() or result.tag
                excerpt = (result.text or "").strip()
                failures.append(
                    Failure(
                        test=test,
                        message=message[:_MAX_MESSAGE_CHARS],
                        log_path=path,
                        line=None,
                        raw_excerpt=excerpt[: self._max_excerpt_chars],
                    )
                )
        return failures
