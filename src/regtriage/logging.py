"""Structured logging and secret redaction utilities for RegTriage."""

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

_SECRET_PLACEHOLDER = "[REDACTED_SECRET]"  # nosec B105: redaction placeholder token, not a real password or secret.

_DEFAULT_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "[REDACTED_PRIVATE_KEY]",
        re.compile(
            r"-----BEGIN\s+[A-Z0-9\s_-]*PRIVATE\s+KEY-----[\s\S]*?-----END\s+[A-Z0-9\s_-]*PRIVATE\s+KEY-----",
            re.IGNORECASE,
        ),
    ),
    (
        "[REDACTED_ANTHROPIC_KEY]",
        re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}", re.ASCII),
    ),
    (
        "[REDACTED_BEARER_TOKEN]",
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    ),
    (
        _SECRET_PLACEHOLDER,
        re.compile(
            r"(?i)\b([A-Za-z0-9_-]*(?:api[-_]?key|secret|token|password)[A-Za-z0-9_-]*)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{12,})['\"]?",
        ),
    ),
    (
        "[REDACTED_EMAIL]",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
)


class SecretRedactor:
    """Detects and redacts sensitive credentials, private keys, and emails."""

    def __init__(
        self,
        custom_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
    ) -> None:
        patterns: list[tuple[str, re.Pattern[str]]] = list(_DEFAULT_REDACTION_PATTERNS)
        if custom_patterns:
            patterns.extend(custom_patterns)
        self._patterns = tuple(patterns)

    def redact(self, text: str) -> str:
        """Replace all identified sensitive occurrences in text with redaction tokens."""
        if not text:
            return text

        result = text
        for token, pattern in self._patterns:
            if token == _SECRET_PLACEHOLDER:
                result = pattern.sub(f"\\1={_SECRET_PLACEHOLDER}", result)
            else:
                result = pattern.sub(token, result)
        return result


class RedactingFormatter(logging.Formatter):
    """Logging formatter that sanitizes log records via SecretRedactor."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        json_format: bool = False,
        redactor: SecretRedactor | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.json_format = json_format
        self.redactor = redactor if redactor is not None else SecretRedactor()

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record and redact sensitive content."""
        if self.json_format:
            raw_message = record.getMessage()
            clean_message = self.redactor.redact(raw_message)
            payload: dict[str, Any] = {
                "timestamp": self.formatTime(record, self.datefmt),
                "logger": record.name,
                "level": record.levelname,
                "message": clean_message,
            }
            if record.exc_info:
                exc_text = self.formatException(record.exc_info)
                payload["exception"] = self.redactor.redact(exc_text)
            return json.dumps(payload, ensure_ascii=False)

        formatted = super().format(record)
        return self.redactor.redact(formatted)


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
    redactor: SecretRedactor | None = None,
) -> None:
    """Configure RegTriage root logger handlers with sanitizing formatter."""
    logger = logging.getLogger("regtriage")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)

    formatter = RedactingFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        json_format=json_format,
        redactor=redactor,
    )
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a scoped child logger inside the regtriage hierarchy."""
    if name.startswith("regtriage.") or name == "regtriage":
        return logging.getLogger(name)
    return logging.getLogger(f"regtriage.{name}")
