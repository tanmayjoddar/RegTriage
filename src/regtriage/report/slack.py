"""Optional Slack webhook delivery for the Markdown report.

The webhook URL arrives as a SecretStr loaded from the environment by the
caller (never argv, never logs). Delivery uses stdlib urllib with a timeout
on every call; failures raise ExecutionError whose message never contains
the URL.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from pydantic import SecretStr

from regtriage.errors import ExecutionError

_DEFAULT_TIMEOUT_SECONDS = 15.0
_MAX_BODY_CHARS = 256_000
_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _checked_url(webhook_url: SecretStr) -> str:
    """Allow https webhooks (http only for loopback test stubs); reject rest."""
    raw = webhook_url.get_secret_value()
    parts = urllib.parse.urlparse(raw)
    if parts.scheme == "https":
        return raw
    if parts.scheme == "http" and parts.hostname in _ALLOWED_LOOPBACK_HOSTS:
        return raw
    raise ExecutionError(
        "slack webhook URL must use https (http is only for loopback test stubs)",
        timed_out=False,
    )


def send_slack(
    webhook_url: SecretStr,
    markdown: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """POST the report text to a Slack incoming webhook."""
    if timeout_seconds <= 0:
        raise ExecutionError(
            "slack timeout must be positive",
            timed_out=False,
        )
    body = json.dumps({"text": markdown[:_MAX_BODY_CHARS]}).encode("utf-8")
    request = urllib.request.Request(
        _checked_url(webhook_url),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # nosec B310: scheme allowlisted by _checked_url above.
            request, timeout=timeout_seconds
        ) as response:
            status = getattr(response, "status", 200)
    except TimeoutError as exc:
        raise ExecutionError("slack webhook timed out", timed_out=True) from exc
    except urllib.error.HTTPError as exc:
        raise ExecutionError(
            f"slack webhook failed with status {exc.code}",
            returncode=exc.code,
            timed_out=False,
        ) from exc
    except OSError as exc:
        raise ExecutionError(f"slack webhook delivery failed: {exc}", timed_out=False) from exc
    if status != 200:
        raise ExecutionError(
            f"slack webhook failed with status {status}",
            returncode=status,
            timed_out=False,
        )
