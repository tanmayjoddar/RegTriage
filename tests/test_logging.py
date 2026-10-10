"""Tests for structured logging and secret redaction."""

import json
import logging
import re

from regtriage.logging import (
    RedactingFormatter,
    SecretRedactor,
    configure_logging,
    get_logger,
)


def test_redact_anthropic_api_key() -> None:
    redactor = SecretRedactor()
    secret_text = "Connecting with key sk-ant-api03-abcdef1234567890abcdef1234567890 to service"
    clean = redactor.redact(secret_text)
    assert "sk-ant-api03" not in clean
    assert "[REDACTED_ANTHROPIC_KEY]" in clean
    assert clean == "Connecting with key [REDACTED_ANTHROPIC_KEY] to service"


def test_redact_bearer_token() -> None:
    redactor = SecretRedactor()
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.secret"
    clean = redactor.redact(raw)
    assert "eyJhbGci" not in clean
    assert "Authorization: [REDACTED_BEARER_TOKEN]" in clean


def test_redact_secrets_in_key_value() -> None:
    redactor = SecretRedactor()
    raw = "api_key=very_secret_passphrase_12345 and token: 'supersecrettoken98765'"
    clean = redactor.redact(raw)
    assert "very_secret_passphrase_12345" not in clean
    assert "supersecrettoken98765" not in clean
    assert "[REDACTED_SECRET]" in clean


def test_redact_private_key() -> None:
    redactor = SecretRedactor()
    pk = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Yv+3Gq7m4s...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    clean = redactor.redact(f"Loaded credentials:\n{pk}\nDone.")
    assert "MIIEowIBAAKCAQEA" not in clean
    assert "[REDACTED_PRIVATE_KEY]" in clean


def test_redact_email() -> None:
    redactor = SecretRedactor()
    raw = "Contact engineer at alex.forencich@example.com for review"
    clean = redactor.redact(raw)
    assert "alex.forencich@example.com" not in clean
    assert "[REDACTED_EMAIL]" in clean


def test_redact_empty_or_clean_text() -> None:
    redactor = SecretRedactor()
    assert redactor.redact("") == ""
    normal = "PCIe regression finished: 42 passed, 2 failed."
    assert redactor.redact(normal) == normal


def test_custom_redaction_pattern() -> None:
    custom_pattern = ("[REDACTED_INTERNAL_IP]", re.compile(r"10\.240\.\d+\.\d+"))
    redactor = SecretRedactor(custom_patterns=[custom_pattern])
    text = "Slurm cluster node 10.240.12.34 running sim"
    clean = redactor.redact(text)
    assert "10.240.12.34" not in clean
    assert "[REDACTED_INTERNAL_IP]" in clean


def test_redacting_formatter_human() -> None:
    formatter = RedactingFormatter(
        fmt="%(levelname)s - %(message)s",
        json_format=False,
    )
    record = logging.LogRecord(
        name="regtriage.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="API call failed with token sk-ant-1234567890123456789012345",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    assert "sk-ant-" not in output
    assert "[REDACTED_ANTHROPIC_KEY]" in output


def test_redacting_formatter_json() -> None:
    formatter = RedactingFormatter(json_format=True)
    try:
        raise ValueError("Sensitive error: secret_key=secretpassword123456")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="regtriage.agent",
        level=logging.ERROR,
        pathname="agent.py",
        lineno=42,
        msg="Failed dispatch: Bearer token1234567890123456",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert data["logger"] == "regtriage.agent"
    assert data["level"] == "ERROR"
    assert "token1234567890123456" not in data["message"]
    assert "[REDACTED_BEARER_TOKEN]" in data["message"]
    assert "secretpassword123456" not in data["exception"]
    assert "[REDACTED_SECRET]" in data["exception"]


def test_configure_logging_and_get_logger() -> None:
    configure_logging(level="DEBUG", json_format=False)
    logger1 = get_logger("runner")
    assert logger1.name == "regtriage.runner"

    logger2 = get_logger("regtriage.parsing")
    assert logger2.name == "regtriage.parsing"

    # Calling configure_logging repeatedly is idempotent
    configure_logging(level="INFO", json_format=True)
    root = logging.getLogger("regtriage")
    assert len(root.handlers) == 1
    assert root.level == logging.INFO
