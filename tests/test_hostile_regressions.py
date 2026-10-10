"""Hostile-review regression tests: probes that once failed, pinned forever.

Each test below reproduces a confirmed finding from the hostile review
(numbered per the review). They must never be weakened: if one fails, the
hole is back.
"""

import pytest

from regtriage.agent import LlmRequest, LlmResponse, ReplayClient
from regtriage.agent.protocol import TextBlock
from regtriage.errors import AgentLoopError, BudgetExceeded
from regtriage.eval.harness import MeteredClient


def _request() -> LlmRequest:
    return LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={})


def _response(in_tokens: int = 0, out_tokens: int = 0) -> LlmResponse:
    return LlmResponse(
        content=[TextBlock(text="ok")],
        stop_reason="end_turn",
        input_tokens=in_tokens,
        output_tokens=out_tokens,
    )


def test_probe_6_blocks_call_over_budget_before_sending() -> None:
    inner = ReplayClient([_response(), _response()])
    metered = MeteredClient(inner, max_calls=1, max_usd=100.0)
    metered.create_message(_request())
    with pytest.raises(BudgetExceeded):
        metered.create_message(_request())
    assert len(inner.requests) == 1


def test_probe_6_blocks_spend_over_budget_before_sending() -> None:
    inner = ReplayClient([_response(in_tokens=1_000_000), _response()])
    metered = MeteredClient(inner, max_calls=100, max_usd=1.0)
    metered.create_message(_request())
    assert metered.usd == pytest.approx(2.0)
    with pytest.raises(BudgetExceeded):
        metered.create_message(_request())
    assert len(inner.requests) == 1


def test_probe_6_budget_exceeded_is_agent_loop_error() -> None:
    assert issubclass(BudgetExceeded, AgentLoopError)
    err = BudgetExceeded("over")
    assert isinstance(err, AgentLoopError)
    assert err.to_dict()["error_type"] == "BudgetExceeded"


def test_fix_6_boundary_call_allowed_then_blocked() -> None:
    inner = ReplayClient([_response(), _response(), _response()])
    metered = MeteredClient(inner, max_calls=2, max_usd=100.0)
    metered.create_message(_request())
    metered.create_message(_request())
    assert len(inner.requests) == 2
    with pytest.raises(BudgetExceeded):
        metered.create_message(_request())
    assert len(inner.requests) == 2
    assert metered.llm_calls == 2


def test_fix_6_blocked_call_freezes_counters() -> None:
    inner = ReplayClient([_response(in_tokens=1_000_000)])
    metered = MeteredClient(inner, max_calls=100, max_usd=1.0)
    metered.create_message(_request())
    before = (metered.llm_calls, metered.input_tokens, len(inner.requests))
    with pytest.raises(BudgetExceeded):
        metered.create_message(_request())
    assert (metered.llm_calls, metered.input_tokens, len(inner.requests)) == before


def test_fix_6_rejects_nonsense_ceilings() -> None:
    from regtriage.errors import ConfigurationError

    inner = ReplayClient([_response()])
    with pytest.raises(ConfigurationError):
        MeteredClient(inner, max_calls=0, max_usd=1.0)
    with pytest.raises(ConfigurationError):
        MeteredClient(inner, max_calls=1, max_usd=-0.5)


def test_probe_3_aws_key_redacted() -> None:
    from regtriage.logging import SecretRedactor

    clean = SecretRedactor().redact("key AKIAIOSFODNN7EXAMPLE leaked")
    assert "AKIAIOSFODNN7EXAMPLE" not in clean


def test_probe_3_github_tokens_redacted() -> None:
    from regtriage.logging import SecretRedactor

    redactor = SecretRedactor()
    assert "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in redactor.redact(
        "token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx here"
    )
    assert "github_pat_abc123_DEF456" not in redactor.redact("t github_pat_abc123_DEF456 x")


def test_probe_3_slack_and_jwt_redacted() -> None:
    from regtriage.logging import SecretRedactor

    redactor = SecretRedactor()
    assert "xoxb-123456-DEADBEEF" not in redactor.redact("hook xoxb-123456-DEADBEEF end")
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert jwt not in redactor.redact(f"auth {jwt} done")


def test_probe_3_json_secrets_redacted() -> None:
    from regtriage.logging import SecretRedactor

    clean = SecretRedactor().redact('{"api_key": "supersecretvalue123", "user": "bob"}')
    assert "supersecretvalue123" not in clean
    assert '"user": "bob"' in clean


def test_probe_3_password_is_phrase_redacted() -> None:
    from regtriage.logging import SecretRedactor

    clean = SecretRedactor().redact("the password is hunter2hunter2 ok")
    assert "hunter2hunter2" not in clean


def test_fix_3_mixed_secrets_all_redacted_prose_kept() -> None:
    from regtriage.logging import SecretRedactor

    raw = (
        "deploy started AKIAIOSFODNN7EXAMPLE with ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx "
        'and {"token": "abc123def456ghi789jkl012mno345pq"} then password is s3cr3t-s3cr3t done'
    )
    clean = SecretRedactor().redact(raw)
    for secret in (
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "abc123def456ghi789jkl012mno345pq",
        "s3cr3t-s3cr3t",
    ):
        assert secret not in clean
    assert "deploy started" in clean and "done" in clean


def test_fix_3_boundaries_and_case_variants() -> None:
    from regtriage.logging import SecretRedactor

    redactor = SecretRedactor()
    assert "AKIAIOSFODNN7EXAMPLE" not in redactor.redact("AKIAIOSFODNN7EXAMPLE")
    assert "xoxp-99-zz" not in redactor.redact("trailing xoxp-99-zz")
    assert "Hunter2Hunter2" not in redactor.redact("Password IS Hunter2Hunter2!")
    assert '"apiKey": "[REDACTED_SECRET]"' in redactor.redact('{"apiKey": "Kk9 offshore value 1"}')


def test_fix_3_lookalikes_untouched() -> None:
    from regtriage.logging import SecretRedactor

    redactor = SecretRedactor()
    assert redactor.redact("AKIA too short here") == "AKIA too short here"
    assert redactor.redact("xox alone means nothing") == "xox alone means nothing"
    assert redactor.redact("eyJ only two segments here") == "eyJ only two segments here"
    assert redactor.redact("passwords are hashed") == "passwords are hashed"
    assert redactor.redact('{"user": "bob"}') == '{"user": "bob"}'
