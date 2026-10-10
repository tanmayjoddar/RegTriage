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
