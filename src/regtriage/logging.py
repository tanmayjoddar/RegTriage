"""Structured logging and secret redaction utilities for RegTriage."""

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

_SECRET_PLACEHOLDER = "[REDACTED_SECRET]"  # nosec B105: redaction placeholder token, not a real password or secret.
_PASSWORD_PHRASE_TOKEN = "[REDACTED_PASSWORD_PHRASE]"  # nosec B105: redaction placeholder token, not a real password or secret.

# Tokens whose replacement is not the token itself map to an explicit
# substitution template here; every other token replaces the whole match.
_SPECIAL_REPLACEMENTS: dict[str, str] = {
    _PASSWORD_PHRASE_TOKEN: "password is [REDACTED_SECRET]",
}

# A JSON-ish key counts as secret-bearing when the whole key matches.
_SECRET_KEY_RE = re.compile(r"(?:api[-_]?key|secret|token|password)[A-Za-z0-9_-]*\Z", re.IGNORECASE)

_WS_CHARS = " \t\r\n"


def _scan_quoted(text: str, start: int) -> tuple[str, int] | None:
    """Parse one quoted string starting at `start` (a `"` or `'`).

    Backslash escapes are honored, so an escaped quote never ends the
    string early. Returns (unescaped value, index just past the closer),
    or None when unterminated.
    """
    quote = text[start]
    out: list[str] = []
    i = start + 1
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
            continue
        if char == quote:
            return "".join(out), i + 1
        out.append(char)
        i += 1
    return None


def _redact_json_pairs(text: str) -> str:
    """Redact `"key": "value"` / `'key': 'value'` pairs with secret keys.

    Small tokenizer, not a regex: string literals are scanned with escape
    handling, so values containing escaped quotes are fully consumed and
    single-quoted pairs match too. Non-pair literals are copied verbatim
    (O(n) total: each literal is scanned once). The key keeps its original
    quoting; the value becomes `"[REDACTED_SECRET]"`.
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char not in "\"'":
            out.append(char)
            i += 1
            continue
        parsed = _scan_quoted(text, i)
        if parsed is None:
            out.append(char)
            i += 1
            continue
        key, key_end = parsed
        if _SECRET_KEY_RE.match(key) is None:
            out.append(text[i:key_end])
            i = key_end
            continue
        j = key_end
        while j < len(text) and text[j] in _WS_CHARS:
            j += 1
        if j >= len(text) or text[j] != ":":
            out.append(text[i:key_end])
            i = key_end
            continue
        j += 1
        while j < len(text) and text[j] in _WS_CHARS:
            j += 1
        if j >= len(text) or text[j] not in "\"'":
            out.append(text[i:key_end])
            i = key_end
            continue
        value_parsed = _scan_quoted(text, j)
        if value_parsed is None:
            out.append(text[i:key_end])
            i = key_end
            continue
        _, value_end = value_parsed
        out.append(text[i:key_end])
        out.append(': "[REDACTED_SECRET]"')
        i = value_end
    return "".join(out)


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
        "[REDACTED_AWS_KEY]",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b", re.ASCII),
    ),
    (
        "[REDACTED_GITHUB_TOKEN]",
        re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]+)\b", re.ASCII),
    ),
    (
        "[REDACTED_SLACK_TOKEN]",
        re.compile(r"\bxox[bpars]-[A-Za-z0-9-]+\b", re.ASCII),
    ),
    (
        "[REDACTED_BEARER_TOKEN]",
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    ),
    (
        "[REDACTED_JWT]",
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", re.ASCII),
    ),
    (
        _PASSWORD_PHRASE_TOKEN,
        re.compile(r"password\s+is\s+[A-Za-z0-9_.\-~+/=]{4,}", re.IGNORECASE),
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

        # JSON-ish pairs first: the tokenizer consumes whole quoted values
        # (escapes included), so later key=value rules see canonical text.
        result = _redact_json_pairs(text)
        for token, pattern in self._patterns:
            special = _SPECIAL_REPLACEMENTS.get(token)
            if special is not None:
                result = pattern.sub(special, result)
            elif token == _SECRET_PLACEHOLDER:
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
