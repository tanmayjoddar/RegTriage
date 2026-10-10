"""Hostile-review regression tests: probes that once failed, pinned forever.

Each test below reproduces a confirmed finding from the hostile review
(numbered per the review). They must never be weakened: if one fails, the
hole is back.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from regtriage.agent import LlmRequest, LlmResponse, ReplayClient, triage_cluster
from regtriage.agent.protocol import TextBlock, ToolUseBlock
from regtriage.agent.tooling import SUBMIT_DIAGNOSIS
from regtriage.audit import AuditLogger
from regtriage.config import RegTriageConfig
from regtriage.errors import AgentLoopError, BudgetExceeded
from regtriage.eval.harness import MeteredClient
from regtriage.parsing import Failure
from regtriage.signature import Cluster


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


def _cluster_for(root: Path, message: str = "boom") -> Cluster:
    return Cluster(
        cluster_id="cluster-001",
        signature="s",
        members=[Failure(test="t", message=message, raw_excerpt="")],
    )


def _minimal_submit() -> dict[str, Any]:
    return {
        "cluster_id": "cluster-001",
        "root_cause_summary": "x",
        "confidence": 0.1,
        "status": "failed",
    }


def test_probe_4_model_text_scrubbed_before_resend_and_audit(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("line one\n", encoding="utf-8")
    leaked = "sk-ant-12345678901234567890123456789012"
    script = [
        LlmResponse(
            content=[TextBlock(text=f"thinking about {leaked} here")],
            stop_reason="end_turn",
            input_tokens=1,
            output_tokens=1,
        ),
        LlmResponse(
            content=[ToolUseBlock(id="s1", name=SUBMIT_DIAGNOSIS, input=_minimal_submit())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = ReplayClient(script)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    config = RegTriageConfig(workspace_root=root, model_id="m")
    diagnosis = triage_cluster(
        client=client,
        config=config,
        root=root,
        cluster=_cluster_for(root),
        audit=audit,
    )
    assert diagnosis.status == "failed"
    assert leaked not in json.dumps([r.model_dump() for r in client.requests[1:]])
    logged = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert leaked not in logged
    assert "[REDACTED_ANTHROPIC_KEY]" in logged


def test_fix_4_nested_inputs_scrubbed_types_kept(tmp_path: Path) -> None:
    from regtriage.agent.loop import _scrub_response
    from regtriage.logging import SecretRedactor

    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    response = LlmResponse(
        content=[
            ToolUseBlock(
                id="u1",
                name="grep_source",
                input={"pattern": jwt, "opts": ["a", 5, None, True], "nested": {"k": jwt}},
            )
        ],
        stop_reason="tool_use",
        input_tokens=0,
        output_tokens=0,
    )
    scrubbed = _scrub_response(response, SecretRedactor())
    (block,) = scrubbed.content
    assert isinstance(block, ToolUseBlock)
    assert jwt not in json.dumps(block.input)
    assert block.input["opts"] == ["a", 5, None, True]
    assert block.input["nested"]["k"] == "[REDACTED_JWT]"
    (original,) = response.content
    assert isinstance(original, ToolUseBlock)
    assert original.input["pattern"] == jwt


def test_fix_4_audit_matches_exactly_what_was_sent(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("line one\n", encoding="utf-8")
    script = [
        LlmResponse(
            content=[TextBlock(text="note xoxb-1-abc here")],
            stop_reason="end_turn",
            input_tokens=2,
            output_tokens=3,
        ),
        LlmResponse(
            content=[ToolUseBlock(id="s1", name=SUBMIT_DIAGNOSIS, input=_minimal_submit())],
            stop_reason="tool_use",
            input_tokens=2,
            output_tokens=3,
        ),
    ]
    client = ReplayClient(script)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    config = RegTriageConfig(workspace_root=root, model_id="m")
    triage_cluster(client=client, config=config, root=root, cluster=_cluster_for(root), audit=audit)
    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["kind"] for r in records] == ["request", "response", "request", "response"]
    assert records[0]["payload"] == client.requests[0].model_dump(mode="json")
    assert records[2]["payload"] == client.requests[1].model_dump(mode="json")
    assert "xoxb-1-abc" not in json.dumps(records)
    assert "[REDACTED_SLACK_TOKEN]" in json.dumps(records)


def test_fix_4_hallucinated_secret_in_prose_scrubbed(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("line one\n", encoding="utf-8")
    invented = "github_pat_" + "Q" * 40
    script = [
        LlmResponse(
            content=[TextBlock(text=f"I recall the key {invented} from training")],
            stop_reason="end_turn",
            input_tokens=1,
            output_tokens=1,
        ),
        LlmResponse(
            content=[ToolUseBlock(id="s1", name=SUBMIT_DIAGNOSIS, input=_minimal_submit())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = ReplayClient(script)
    config = RegTriageConfig(workspace_root=root, model_id="m")
    triage_cluster(client=client, config=config, root=root, cluster=_cluster_for(root))
    assert invented not in json.dumps(client.requests[1].model_dump())


def test_probe_4_tool_input_scrubbed_in_echo_but_executed_raw(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    shaped = "AKIAIOSFODNN7EXAMPLE"
    (root / "sim.log").write_text(f"line one\nnote {shaped} here\n", encoding="utf-8")
    script = [
        LlmResponse(
            content=[ToolUseBlock(id="u1", name="grep_source", input={"pattern": shaped})],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
        LlmResponse(
            content=[ToolUseBlock(id="s1", name=SUBMIT_DIAGNOSIS, input=_minimal_submit())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = ReplayClient(script)
    config = RegTriageConfig(workspace_root=root, model_id="m")
    triage_cluster(client=client, config=config, root=root, cluster=_cluster_for(root))
    dumped = json.dumps(client.requests[1].model_dump())
    assert shaped not in dumped
    assert "sim.log" in dumped
    assert "[REDACTED_AWS_KEY]" in dumped


def _ws_with(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "ws"
    root.mkdir(exist_ok=True)
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_probe_7_default_search_is_literal(tmp_path: Path) -> None:
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"a.txt": "value (a+)+$ here\naaaa\n"})
    hits = grep_source(root, "(a+)+$")
    assert [(h.path, h.line) for h in hits] == [("a.txt", 1)]


def test_probe_7_regex_meta_needs_opt_in(tmp_path: Path) -> None:
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"a.txt": "a|b literal\na alone\nb alone\n"})
    assert [(h.path, h.line) for h in grep_source(root, "a|b")] == [("a.txt", 1)]
    assert len(grep_source(root, "a|b", fixed_strings=False)) == 3


def test_probe_7_catastrophic_regex_killed_by_timeout(tmp_path: Path) -> None:
    import time as _time

    from regtriage.errors import SandboxViolationError
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"evil.txt": "a" * 100 + "!\n"})
    started = _time.monotonic()
    with pytest.raises(SandboxViolationError) as exc_info:
        grep_source(root, "(a+)+$", fixed_strings=False, regex_timeout_seconds=0.5)
    assert _time.monotonic() - started < 10.0
    assert exc_info.value.violation_type == "regex_timeout"


def test_fix_7_empty_pattern_rejected(tmp_path: Path) -> None:
    from regtriage.errors import SandboxViolationError
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"a.txt": "x\n"})
    with pytest.raises(SandboxViolationError) as exc_info:
        grep_source(root, "")
    assert exc_info.value.violation_type == "invalid_pattern"


def test_fix_7_invalid_regex_opt_in_is_clean_error(tmp_path: Path) -> None:
    from regtriage.errors import SandboxViolationError
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"a.txt": "x\n"})
    with pytest.raises(SandboxViolationError) as exc_info:
        grep_source(root, "([a-z]+$", fixed_strings=False)
    assert exc_info.value.violation_type == "invalid_pattern"


def test_fix_7_reasonable_regex_completes_in_time(tmp_path: Path) -> None:
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"a.txt": "alpha\nbeta\ngamma\n"})
    hits = grep_source(root, "(alpha|beta)$", fixed_strings=False, regex_timeout_seconds=5.0)
    assert [(h.path, h.line) for h in hits] == [("a.txt", 1), ("a.txt", 2)]


def test_fix_7_skips_apply_in_regex_mode(tmp_path: Path) -> None:
    from regtriage.tools import grep_source

    root = _ws_with(tmp_path, {"small.txt": "needle here\n"})
    big = root / "big.txt"
    with open(big, "wb") as handle:
        handle.write(b"needle " * 100_000)
    assert [h.path for h in grep_source(root, "needle", fixed_strings=False)] == ["small.txt"]
    assert grep_source(root, "needle.{0,50}here", fixed_strings=False)[0].path == "small.txt"


def test_fix_7_dispatcher_passes_opt_in(tmp_path: Path) -> None:
    from regtriage.agent import ToolRuntime

    root = _ws_with(tmp_path, {"a.txt": "abc 123\n"})
    runtime = ToolRuntime(root)
    assert runtime.dispatch("grep_source", {"pattern": "abc"}) != ""
    out = runtime.dispatch("grep_source", {"pattern": "(abc|zzz)", "fixed_strings": False})
    assert "a.txt:1:" in out
