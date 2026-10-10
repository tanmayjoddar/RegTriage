"""Tests for GeminiClient (google-genai SDK): translation, schema flattening,
budget mapping, backoff, and redaction/audit parity with Anthropic.

All live-wire tests use recording fakes (no network). The single opt-in
live test at the bottom runs only when GEMINI_API_KEY/GOOGLE_API_KEY is set.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from regtriage.agent import (
    ConversationMessage,
    LlmRequest,
    LlmResponse,
    ReplayClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from regtriage.agent.gemini import (
    DEFAULT_GEMINI_MODEL_ID,
    GeminiClient,
    flatten_diagnosis_schema,
)
from regtriage.agent.tooling import SUBMIT_DIAGNOSIS
from regtriage.errors import AgentLoopError, ConfigurationError


def _request(**over: Any) -> LlmRequest:
    base: dict[str, Any] = {
        "model": "gemini-test",
        "system": "sys",
        "messages": [],
        "tools": [],
        "tool_choice": {},
    }
    base.update(over)
    return LlmRequest(**base)


class _FakeModels:
    """Recording stand-in for client.models."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script: list[Any] = []
        self.errors: list[Exception] = []

    def generate_content(self, **kwargs: Any) -> Any:
        """Record kwargs; raise staged errors, else pop staged responses."""
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        if not self.script:
            raise AssertionError("no staged Gemini response left")
        return self.script.pop(0)


class _FakeGeminiSdk:
    """Recording stand-in for google.genai.Client."""

    def __init__(self) -> None:
        self.models = _FakeModels()
        self.seen: list[tuple[str, float]] = []

    def __call__(self, key: str, timeout: float) -> "_FakeGeminiSdk":
        """Act as the client_factory: capture (key, timeout), return self."""
        self.seen.append((key, timeout))
        return self


def _gemini_response(
    parts: list[Any],
    prompt_tokens: int = 0,
    candidate_tokens: int = 0,
    finish_reason: str = "STOP",
) -> Any:
    content = SimpleNamespace(parts=parts, role="model")
    candidate = SimpleNamespace(content=content, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=candidate_tokens)
    return SimpleNamespace(candidates=[candidate], usage_metadata=usage)


def _text_part(text: str) -> Any:
    return SimpleNamespace(text=text, function_call=None)


def _call_part(name: str, args: dict[str, Any], call_id: str = "call-1") -> Any:
    return SimpleNamespace(
        text=None, function_call=SimpleNamespace(name=name, args=args, id=call_id)
    )


def _client(
    fake: _FakeGeminiSdk, **over: Any
) -> GeminiClient:
    params: dict[str, Any] = {"client_factory": fake}
    params.update(over)
    return GeminiClient(SecretStr("gemini-test-key"), **params)


def test_flatten_has_no_refs_and_keeps_shape() -> None:
    from regtriage.agent import Diagnosis

    flat = flatten_diagnosis_schema()
    dumped = json.dumps(flat)
    assert "$ref" not in dumped and "$defs" not in dumped
    assert flat["title"] == Diagnosis.model_json_schema()["title"]
    assert set(flat["properties"]) == set(Diagnosis.model_json_schema()["properties"])
    evidence = flat["properties"]["evidence"]["items"]
    assert "kind" in evidence["properties"]
    assert set(evidence["required"]) == set(
        Diagnosis.model_json_schema()["$defs"]["Evidence"]["required"]
    )


def test_request_translation_text_and_tool_result_names() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("done")]))
    client = _client(fake)
    request = _request(
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": "look at this"}],
            },
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "u1", "name": "grep_source", "input": {"pattern": "x"}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "u1", "content": "hit", "is_error": False}],
            },
        ]
    )
    response = client.create_message(request)
    assert isinstance(response.content[0], TextBlock)
    sent = fake.models.calls[0]
    assert sent["model"] == "gemini-test"
    roles = [c.role for c in sent["contents"]]
    assert roles == ["user", "model", "user"]
    tool_content = sent["contents"][2]
    fr = tool_content.parts[0].function_response
    assert fr.name == "grep_source"
    assert fr.response == {"result": "hit"}
    assert fr.id == "u1"
    assert sent["config"].system_instruction == "sys"
    assert sent["config"].automatic_function_calling.disable is True


def test_forced_submit_uses_any_with_allowed_name() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    client = _client(fake)
    client.create_message(_request(tool_choice={"type": "tool", "name": SUBMIT_DIAGNOSIS}))
    fcc = fake.models.calls[0]["config"].tool_config.function_calling_config
    assert str(fcc.mode).endswith("ANY")
    assert list(fcc.allowed_function_names) == [SUBMIT_DIAGNOSIS]


def test_auto_tool_choice_maps_to_auto() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    client = _client(fake)
    client.create_message(_request(tool_choice={"type": "auto"}))
    fcc = fake.models.calls[0]["config"].tool_config.function_calling_config
    assert str(fcc.mode).endswith("AUTO")


def test_response_usage_maps_to_cost_guard() -> None:
    from regtriage.eval.harness import MeteredClient

    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("ok")], prompt_tokens=1_000_000))
    inner_client = _client(fake)
    metered = MeteredClient(inner_client, max_calls=100, max_usd=100.0)
    metered.create_message(_request(model=DEFAULT_GEMINI_MODEL_ID))
    assert metered.input_tokens == 1_000_000
    assert metered.usd == pytest.approx(0.75)
    with pytest.raises(AgentLoopError):
        metered.check_budget(100, 0.5)


def test_metered_client_fails_loudly_on_unpriced_model() -> None:
    from regtriage.eval.harness import MeteredClient

    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("ok")], prompt_tokens=1_000))
    inner_client = _client(fake)
    metered = MeteredClient(inner_client, max_calls=100, max_usd=100.0)
    with pytest.raises(ConfigurationError, match="no estimated token pricing"):
        metered.create_message(_request(model="unknown-gemini-model"))


def test_function_call_round_trip_with_ids() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(
        _gemini_response([_call_part("read_log_lines", {"path": "sim.log"}, call_id="c9")])
    )
    client = _client(fake)
    response = client.create_message(_request())
    (block,) = response.content
    assert isinstance(block, ToolUseBlock)
    assert (block.id, block.name, block.input) == ("c9", "read_log_lines", {"path": "sim.log"})
    assert (response.input_tokens, response.output_tokens) == (0, 0)


def test_unknown_part_shape_is_clean_error() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([SimpleNamespace(text=None, function_call=None)]))
    client = _client(fake)
    with pytest.raises(AgentLoopError):
        client.create_message(_request())


def test_retry_then_success_on_429() -> None:
    from google.genai import errors as _errors

    fake = _FakeGeminiSdk()
    sleeps: list[float] = []
    err = _errors.APIError(429, {"error": {"message": "slow down"}}, None)
    fake.models.errors.extend([err, err])
    fake.models.script.append(_gemini_response([_text_part("recovered")]))
    client = _client(fake, sleeper=sleeps.append)
    response = client.create_message(_request())
    assert isinstance(response.content[0], TextBlock)
    assert len(fake.models.calls) == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] >= 1.0


def test_retry_hint_honored_and_capped() -> None:
    from google.genai import errors as _errors

    fake = _FakeGeminiSdk()
    sleeps: list[float] = []
    hinted = _errors.APIError(
        503,
        {"error": {"details": [{"retryDelay": "45.0s"}]}},
        None,
    )
    fake.models.errors.append(hinted)
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    client = _client(fake, sleeper=sleeps.append)
    client.create_message(_request())
    assert sleeps == [30.0]


def test_retry_hint_bare_error_dict() -> None:
    from google.genai import errors as _errors

    fake = _FakeGeminiSdk()
    sleeps: list[float] = []
    hinted = _errors.APIError(
        503,
        {"details": [{"retryDelay": "5.5s"}]},
        None,
    )
    fake.models.errors.append(hinted)
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    client = _client(fake, sleeper=sleeps.append)
    client.create_message(_request())
    assert sleeps == [5.5]


def test_retry_hint_response_json_fallback() -> None:
    fake = _FakeGeminiSdk()
    sleeps: list[float] = []

    class _CustomHttpError(Exception):
        status_code = 503
        response_json = {"error": {"details": [{"retryDelay": "3.5s"}]}}

    fake.models.errors.append(_CustomHttpError("server busy"))
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    client = _client(fake, sleeper=sleeps.append)
    client.create_message(_request())
    assert sleeps == [3.5]



def test_non_retryable_fails_without_sleep() -> None:
    from google.genai import errors as _errors

    fake = _FakeGeminiSdk()
    sleeps: list[float] = []
    fake.models.errors.append(_errors.APIError(400, {"error": {"message": "bad"}}, None))
    client = _client(fake, sleeper=sleeps.append)
    with pytest.raises(AgentLoopError):
        client.create_message(_request())
    assert sleeps == [] and len(fake.models.calls) == 1


def test_retries_bounded() -> None:
    from google.genai import errors as _errors

    fake = _FakeGeminiSdk()
    sleeps: list[float] = []
    for _ in range(10):
        fake.models.errors.append(_errors.APIError(503, {"error": {}}, None))
    client = _client(fake, max_retries=2, sleeper=sleeps.append)
    with pytest.raises(AgentLoopError):
        client.create_message(_request())
    assert len(fake.models.calls) == 3 and len(sleeps) == 2


def test_rejects_empty_key_and_bad_params() -> None:
    fake = _FakeGeminiSdk()
    with pytest.raises(ConfigurationError):
        GeminiClient(SecretStr("   "), client_factory=fake)
    with pytest.raises(ConfigurationError):
        GeminiClient(SecretStr("k"), timeout_seconds=0, client_factory=fake)
    with pytest.raises(ConfigurationError):
        GeminiClient(SecretStr("k"), max_retries=-1, client_factory=fake)


def test_key_travels_only_into_factory() -> None:
    fake = _FakeGeminiSdk()
    fake.models.script.append(_gemini_response([_text_part("ok")]))
    _client(fake).create_message(_request())
    assert fake.seen == [("gemini-test-key", 60.0)]
    assert "gemini-test-key" not in json.dumps(fake.models.calls, default=str)


def test_gemini_triage_redaction_and_audit_parity(tmp_path: Path) -> None:
    from regtriage.agent import triage_cluster
    from regtriage.audit import AuditLogger
    from regtriage.config import RegTriageConfig
    from regtriage.parsing import Failure
    from regtriage.signature import Cluster

    secret = "AKIAIOSFODNN7EXAMPLE"
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text(f"leak {secret} here\n", encoding="utf-8")
    fake = _FakeGeminiSdk()
    fake.models.script.append(
        _gemini_response([_call_part("read_log_lines", {"path": "sim.log"})])
    )
    fake.models.script.append(
        _gemini_response(
            [
                _call_part(
                    "submit_diagnosis",
                    {
                        "cluster_id": "cluster-001",
                        "root_cause_summary": "x",
                        "confidence": 0.1,
                        "status": "failed",
                    },
                )
            ]
        )
    )
    backend = _client(fake)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    cluster = Cluster(
        cluster_id="cluster-001", signature="s", members=[Failure(test="t", message="m", raw_excerpt="")]
    )
    diagnosis = triage_cluster(
        client=backend, config=RegTriageConfig(workspace_root=root, model_id="m"), root=root, cluster=cluster, audit=audit
    )
    assert diagnosis.status == "failed"
    assert secret not in json.dumps(fake.models.calls, default=str)
    assert secret not in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_provider_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from regtriage.config import DEFAULT_GEMINI_MODEL_ID, load_config

    monkeypatch.setenv("REGTRIAGE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    config = load_config(env=dict(__import__("os").environ))
    assert config.provider == "gemini"
    assert config.gemini_api_key is not None
    assert config.gemini_model_id == DEFAULT_GEMINI_MODEL_ID
    assert config.mask_for_logging()["gemini_api_key"] == "[MASKED_KEY]"
    monkeypatch.setenv("REGTRIAGE_GEMINI_MODEL", "gemini-custom")
    config2 = load_config(env=dict(__import__("os").environ))
    assert config2.gemini_model_id == "gemini-custom"


def test_provider_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    from regtriage.config import load_config
    from regtriage.errors import ConfigurationError

    monkeypatch.setenv("REGTRIAGE_PROVIDER", "other")
    with pytest.raises(ConfigurationError):
        load_config(env=dict(__import__("os").environ))


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="live Gemini test needs GEMINI_API_KEY",
)
def test_live_gemini_two_turn_tool_call() -> None:
    key = SecretStr(os.environ["GEMINI_API_KEY"])
    client = GeminiClient(key, max_retries=1)

    # Turn 1: Force tool call to read_log_lines
    turn1_request = _request(
        model=DEFAULT_GEMINI_MODEL_ID,
        system="You are an assistant that calls tools when instructed.",
        messages=[
            ConversationMessage(
                role="user",
                content=[TextBlock(text="Please inspect sim.log using read_log_lines.")],
            )
        ],
        tool_choice={"type": "tool", "name": "read_log_lines"},
    )
    turn1_resp = client.create_message(turn1_request)
    assert any(isinstance(b, ToolUseBlock) for b in turn1_resp.content)
    tool_call = next(b for b in turn1_resp.content if isinstance(b, ToolUseBlock))
    assert tool_call.name == "read_log_lines"

    # Turn 2: Return tool result, model answers with text
    turn2_request = _request(
        model=DEFAULT_GEMINI_MODEL_ID,
        system="You are an assistant that calls tools when instructed.",
        messages=[
            ConversationMessage(
                role="user",
                content=[TextBlock(text="Please inspect sim.log using read_log_lines.")],
            ),
            ConversationMessage(
                role="assistant",
                content=turn1_resp.content,
            ),
            ConversationMessage(
                role="user",
                content=[
                    ToolResultBlock(
                        tool_use_id=tool_call.id,
                        content="Line 1: Test passed cleanly.\nLine 2: End of simulation.",
                    )
                ],
            ),
        ],
        tool_choice={"type": "auto"},
    )
    turn2_resp = client.create_message(turn2_request)
    assert any(isinstance(b, TextBlock) for b in turn2_resp.content)
    assert turn2_resp.input_tokens > 0 or turn2_resp.output_tokens > 0


def test_replay_client_still_works() -> None:
    script = ReplayClient(
        [LlmResponse(content=[TextBlock(text="hi")], stop_reason="end_turn", input_tokens=1, output_tokens=2)]
    )
    out = script.create_message(_request())
    assert out.input_tokens == 1 and len(script.requests) == 1


def test_tool_call_ids_unique_across_turns_when_missing() -> None:
    from regtriage.agent.gemini import _to_gemini_contents

    fake = _FakeGeminiSdk()
    # Turn 1 response: tool_a call with id=None
    fake.models.script.append(
        _gemini_response([SimpleNamespace(text=None, function_call=SimpleNamespace(name="tool_a", args={"x": 1}, id=None))])
    )
    # Turn 2 response: tool_b call with id=None
    fake.models.script.append(
        _gemini_response([SimpleNamespace(text=None, function_call=SimpleNamespace(name="tool_b", args={"y": 2}, id=None))])
    )
    client = _client(fake)
    resp1 = client.create_message(_request(messages=[ConversationMessage(role="user", content=[TextBlock(text="run a")])]))
    assert len(resp1.content) == 1 and isinstance(resp1.content[0], ToolUseBlock)
    call1 = resp1.content[0]

    resp2 = client.create_message(_request(messages=[
        ConversationMessage(role="user", content=[TextBlock(text="run a")]),
        ConversationMessage(role="assistant", content=[call1]),
        ConversationMessage(role="user", content=[ToolResultBlock(tool_use_id=call1.id, content="result_a")]),
    ]))
    assert len(resp2.content) == 1 and isinstance(resp2.content[0], ToolUseBlock)
    call2 = resp2.content[0]

    # The generated IDs must be distinct
    assert call1.id != call2.id

    # And translating the 2-turn conversation must preserve both function names
    multi_turn_request = _request(messages=[
        ConversationMessage(role="user", content=[TextBlock(text="run a")]),
        ConversationMessage(role="assistant", content=[call1]),
        ConversationMessage(role="user", content=[ToolResultBlock(tool_use_id=call1.id, content="result_a")]),
        ConversationMessage(role="assistant", content=[call2]),
        ConversationMessage(role="user", content=[ToolResultBlock(tool_use_id=call2.id, content="result_b")]),
    ])
    contents = _to_gemini_contents(multi_turn_request)
    # Check function names on function response parts
    tool_resp_names = [
        part.function_response.name
        for c in contents
        for part in c.parts
        if getattr(part, "function_response", None) is not None
    ]
    assert tool_resp_names == ["tool_a", "tool_b"]


def test_thought_signature_round_trip_preserved_and_unmangled_and_not_in_audit() -> None:
    from regtriage.agent.gemini import _to_gemini_contents
    from regtriage.agent.loop import _scrub_response
    from regtriage.logging import SecretRedactor

    fake = _FakeGeminiSdk()
    raw_sig = b"opaque-cryptographic-thought-signature-bytes"
    fake.models.script.append(
        _gemini_response([
            SimpleNamespace(
                text=None,
                function_call=SimpleNamespace(name="read_file", args={"path": "top.v"}, id="call-99"),
                thought_signature=raw_sig,
            )
        ])
    )
    client = _client(fake)
    resp = client.create_message(_request())
    assert len(resp.content) == 1
    call = resp.content[0]
    assert isinstance(call, ToolUseBlock)
    # 1. Signature captured exactly on provider_state
    assert call.provider_state == raw_sig

    # 2. Excluded from audit model_dump
    dumped = resp.model_dump()
    assert "provider_state" not in dumped["content"][0]
    assert raw_sig.decode("latin1") not in json.dumps(dumped)

    # 3. Excluded from redaction mangling
    redactor = SecretRedactor()
    scrubbed = _scrub_response(resp, redactor)
    assert scrubbed.content[0].provider_state == raw_sig

    # 4. Attached back to Part when reconstructed in contents
    turn_request = _request(
        messages=[
            ConversationMessage(role="user", content=[TextBlock(text="start")]),
            ConversationMessage(role="assistant", content=[call]),
            ConversationMessage(role="user", content=[ToolResultBlock(tool_use_id=call.id, content="verilog")]),
        ]
    )
    contents = _to_gemini_contents(turn_request)
    model_turn = contents[1]
    assert model_turn.role == "model"
    part = model_turn.parts[0]
    assert getattr(part, "thought_signature", None) == raw_sig


