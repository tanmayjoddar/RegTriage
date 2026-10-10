"""Round-2 hostile regression tests (copied from reviewer test_hostile_r2.py).

Each test below is a verbatim copy of a confirmed round-2 finding; all were
RED when copied and must stay GREEN. Two reviewer cases are NOT copied here
by design: test_r3_base64_secret_redacted and test_r3_line_wrapped_secret
(R3). Per the fix brief, base64/line-wrap handling is intentionally not
added; that residual is documented in docs/THREAT_MODEL.md ("What redaction
still cannot catch") and recorded in docs/HOSTILE_REVIEW.md.
"""

import json
import subprocess
from pathlib import Path

import pytest

from regtriage.agent import LlmResponse, ReplayClient, ToolUseBlock
from regtriage.agent import LlmResponse as LR
from regtriage.agent import ReplayClient as RC
from regtriage.agent.protocol import TextBlock


def _diag(cid: str = "cluster-001") -> dict[str, object]:
    return {"cluster_id": cid, "root_cause_summary": "x", "confidence": 0.1, "status": "failed"}


# --- R1. scrub covers values only: dict KEYS and tool name/id/stop_reason leak ---
def test_r1_secret_in_tool_name_reaches_llm_and_audit(tmp_path: Path) -> None:
    from regtriage.agent import triage_cluster
    from regtriage.audit import AuditLogger
    from regtriage.config import RegTriageConfig
    from regtriage.parsing import Failure
    from regtriage.signature import Cluster

    evil = "AKIAIOSFODNN7EXAMPLE"
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("hi\n", encoding="utf-8")
    script = [
        LlmResponse(
            content=[ToolUseBlock(id="u1", name=evil, input={})],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
        LlmResponse(
            content=[ToolUseBlock(id="s1", name="submit_diagnosis", input=_diag())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = ReplayClient(script)
    audit = AuditLogger(tmp_path / "a.jsonl")
    cl = Cluster(
        cluster_id="cluster-001", signature="s", members=[Failure(test="t", message="m", raw_excerpt="")]
    )
    triage_cluster(
        client=client, config=RegTriageConfig(workspace_root=root, model_id="m"), root=root, cluster=cl, audit=audit
    )
    assert evil not in json.dumps([r.model_dump() for r in client.requests])
    assert evil not in (tmp_path / "a.jsonl").read_text(encoding="utf-8")


def test_r1_secret_dict_key_unscrubbed() -> None:
    from regtriage.agent.loop import _scrub_value
    from regtriage.logging import SecretRedactor

    out = _scrub_value({"AKIAIOSFODNN7EXAMPLE": "x"}, SecretRedactor())
    assert "AKIAIOSFODNN7EXAMPLE" not in json.dumps(out)


# --- R2. JSON string forms the `"[^"]+"` pattern cannot handle ---
def test_r2_json_escaped_quote_fully_redacted() -> None:
    from regtriage.logging import SecretRedactor

    out = SecretRedactor().redact(r'{"token": "abc\"def456ghi789jkl012"}')
    assert "def456ghi789jkl012" not in out


def test_r2_single_quoted_secret_redacted() -> None:
    from regtriage.logging import SecretRedactor

    out = SecretRedactor().redact("{'token': 'abc123def456ghi789jkl012'}")
    assert "abc123def456ghi789jkl012" not in out


# --- B1. per-arm ceilings ignore the global remainder ---
def test_b1_global_budget_not_overshot(tmp_path: Path) -> None:
    from regtriage.eval import SimOutcome
    from regtriage.eval.harness import EvalConfig, run_eval
    from regtriage.parsing import Failure

    src = tmp_path / "src"
    (src / "rtl").mkdir(parents=True)
    (src / "rtl" / "dut.v").write_text(
        "module dut;\n  reg [31:0] len;\n  wire en;\n  always @(posedge clk) begin\n"
        "    if (rst) len <= 0;\n    else if (en) len <= len + 1;\n"
        "    if (len == 10) done <= 1;\n  end\nendmodule\n",
        encoding="utf-8",
    )

    def sim(wd: Path, mod: str) -> SimOutcome:
        if wd.name.startswith("base"):
            return SimOutcome(passed=True)
        return SimOutcome(passed=False, failures=[Failure(test="t0", message="mm", raw_excerpt="")])

    diag = {
        "cluster_id": "cluster-0000",
        "root_cause_summary": "x",
        "confidence": 0.5,
        "status": "verified",
        "evidence": [],
        "suspected_files": [],
        "next_steps": [],
    }

    def factory() -> ReplayClient:
        from regtriage.agent import LlmResponse as LR

        return ReplayClient(
            [
                LR(
                    content=[ToolUseBlock(id=f"a{i}", name="grep_source", input={"pattern": "len"})],
                    stop_reason="tool_use",
                    input_tokens=10,
                    output_tokens=10,
                )
                for i in range(3)
            ]
            + [
                LR(
                    content=[ToolUseBlock(id="s1", name="submit_diagnosis", input=diag)],
                    stop_reason="tool_use",
                    input_tokens=10,
                    output_tokens=10,
                )
            ]
        )

    cfg = EvalConfig(
        repo_root=src,
        modules=["tb/dummy"],
        target_files=["rtl/dut.v"],
        work_root=tmp_path / "work",
        seed=7,
        mutant_count=1,
        max_llm_calls=5,
        max_cost_usd=100000.0,
    )
    rep = run_eval(cfg, sim, factory, pin="abc")
    assert rep.cost.llm_calls <= 5


# --- G1. model sets its own regex kill clock ---
def test_g1_regex_timeout_not_attacker_controlled(tmp_path: Path) -> None:
    from regtriage.agent import ToolRuntime

    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    runtime = ToolRuntime(root)
    with pytest.raises(Exception):
        runtime.dispatch(
            "grep_source", {"pattern": "hello", "fixed_strings": False, "regex_timeout_seconds": 3600.0}
        )


# --- G2. full-corpus stdin per call, no early exit ---
def test_g2_grep_does_not_buffer_whole_corpus(tmp_path: Path) -> None:
    import json as _json

    from regtriage.tools.files import _collect_candidates
    from regtriage.tools.sandbox import resolve_within_root

    big = tmp_path / "big"
    big.mkdir()
    for i in range(100):
        (big / f"f{i:03d}.txt").write_bytes(b"y" * 250000 + b"\n")
    root = resolve_within_root(big, ".")
    cands = _collect_candidates(root, root)
    payload_mb = len(_json.dumps({"files": [ln for _, ln in cands]})) / 1e6
    assert payload_mb < 5.0


# --- D1. ADS stream bypasses name matching (Windows) ---
@pytest.mark.skipif(__import__("os").name != "nt", reason="NTFS-only")
def test_d1_ads_stream_blocked(tmp_path: Path) -> None:
    from regtriage.errors import SandboxViolationError
    from regtriage.tools import read_log_lines

    root = tmp_path / "ws"
    root.mkdir()
    (root / "notes.txt").write_text("harmless\n", encoding="utf-8")
    with open(root / "notes.txt:secret", "w", encoding="utf-8") as f:
        f.write("ADS_SECRET\n")
    with pytest.raises(SandboxViolationError):
        read_log_lines(root, "notes.txt:secret")


# --- C1. NUL-valid-UTF8 binaries citable but never tool-returnable ---
def test_c1_nul_binary_not_citable(tmp_path: Path) -> None:
    if __import__("shutil").which("git") is None:
        pytest.skip("git missing")
    from regtriage.errors import ValidationError
    from regtriage.validation import Evidence, validate_evidence

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.email", "t@e"], cwd=repo, check=True, timeout=60)
    (repo / "a.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    (repo / "blob.bin").write_bytes(b"hello\x00world\nsecond line\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "add"],
        cwd=repo,
        check=True,
        timeout=60,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60, check=True
    ).stdout.strip()
    with pytest.raises(ValidationError):
        validate_evidence(
            repo, Evidence(kind="commit", ref=f"{sha}:blob.bin", line_start=1, line_end=1, quote="hello")
        )


# --- Variant tests: two per fix, covering adjacent bypasses ---
def test_r1_variant_stop_reason_scrubbed(tmp_path: Path) -> None:
    from regtriage.agent import triage_cluster
    from regtriage.audit import AuditLogger
    from regtriage.config import RegTriageConfig
    from regtriage.parsing import Failure
    from regtriage.signature import Cluster
    from regtriage.agent import ReplayClient as RC
    from regtriage.agent import LlmResponse as LR

    evil = "AKIAIOSFODNN7EXAMPLE"
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("hi\n", encoding="utf-8")
    script = [
        LR(
            content=[TextBlock(text="thinking")],
            stop_reason=evil,
            input_tokens=1,
            output_tokens=1,
        ),
        LR(
            content=[ToolUseBlock(id="s1", name="submit_diagnosis", input=_diag())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = RC(script)
    audit = AuditLogger(tmp_path / "a.jsonl")
    cl = Cluster(
        cluster_id="cluster-001", signature="s", members=[Failure(test="t", message="m", raw_excerpt="")]
    )
    triage_cluster(
        client=client, config=RegTriageConfig(workspace_root=root, model_id="m"), root=root, cluster=cl, audit=audit
    )
    assert evil not in json.dumps([r.model_dump() for r in client.requests])
    assert evil not in (tmp_path / "a.jsonl").read_text(encoding="utf-8")


def test_r1_variant_evil_id_echo_scrubbed_but_tool_runs(tmp_path: Path) -> None:
    from regtriage.agent import triage_cluster
    from regtriage.config import RegTriageConfig
    from regtriage.parsing import Failure
    from regtriage.signature import Cluster
    from regtriage.agent import ReplayClient as RC
    from regtriage.agent import LlmResponse as LR

    evil_id = "u-AKIAIOSFODNN7EXAMPLE"
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text("needle here\n", encoding="utf-8")
    script = [
        LR(
            content=[ToolUseBlock(id=evil_id, name="read_log_lines", input={"path": "sim.log"})],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
        LR(
            content=[ToolUseBlock(id="s1", name="submit_diagnosis", input=_diag())],
            stop_reason="tool_use",
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    client = RC(script)
    cl = Cluster(
        cluster_id="cluster-001", signature="s", members=[Failure(test="t", message="m", raw_excerpt="")]
    )
    triage_cluster(
        client=client, config=RegTriageConfig(workspace_root=root, model_id="m"), root=root, cluster=cl
    )
    dumped = json.dumps([r.model_dump() for r in client.requests])
    assert evil_id not in dumped
    assert "[REDACTED_AWS_KEY]" in dumped
    assert "needle here" in dumped


def test_r2_variant_single_quoted_escaped_quote() -> None:
    from regtriage.logging import SecretRedactor

    out = SecretRedactor().redact("{'token': 'ab\\'cd123456789012'}")
    assert "cd123456789012" not in out
    assert "abcd123456789012" not in out


def test_r2_variant_value_with_colon_and_near_miss_key() -> None:
    from regtriage.logging import SecretRedactor

    redactor = SecretRedactor()
    out = redactor.redact('{\n"password" : "a:b:cdefghijklm"\n}')
    assert "a:b:cdefghijklm" not in out
    assert redactor.redact('{"detokenize": "keepme"}') == '{"detokenize": "keepme"}'


def test_b1_variant_shared_usd_blocks_second_arm(tmp_path: Path) -> None:
    from regtriage.agent import LlmRequest
    from regtriage.agent import LlmResponse as LR
    from regtriage.errors import BudgetExceeded
    from regtriage.eval.harness import MeteredClient, _Budget

    def big() -> LR:
        return LR(content=[], stop_reason="end_turn", input_tokens=500_000, output_tokens=0)

    shared = _Budget()
    first = MeteredClient(RC([big()]), max_calls=100, max_usd=100000.0, shared=shared)
    first.create_message(LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={}))
    assert shared.usd == pytest.approx(1.0)
    inner_second = RC([big()])
    second = MeteredClient(inner_second, max_calls=100, max_usd=0.5, shared=shared)
    with pytest.raises(BudgetExceeded):
        second.create_message(LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={}))
    assert len(inner_second.requests) == 0


def test_b1_variant_blocked_call_freezes_shared_counters() -> None:
    from regtriage.agent import LlmRequest
    from regtriage.agent import LlmResponse as LR
    from regtriage.errors import BudgetExceeded
    from regtriage.eval.harness import MeteredClient, _Budget

    shared = _Budget()
    shared.llm_calls = 100
    metered = MeteredClient(
        RC([LR(content=[], stop_reason="end_turn", input_tokens=0, output_tokens=0)]),
        max_calls=100,
        max_usd=100.0,
        shared=shared,
    )
    with pytest.raises(BudgetExceeded):
        metered.create_message(LlmRequest(model="m", system="", messages=[], tools=[], tool_choice={}))
    assert (metered.llm_calls, shared.llm_calls) == (0, 100)


def test_g1_variant_grep_args_reject_timeout_field() -> None:
    from pydantic import ValidationError as PydanticValidationError

    from regtriage.agent.tooling import GrepArgs

    with pytest.raises(PydanticValidationError):
        GrepArgs(pattern="x", regex_timeout_seconds=3600.0)


def test_g1_variant_schema_hides_timeout_but_grep_works(tmp_path: Path) -> None:
    from regtriage.agent import ToolRuntime, agent_tool_schemas

    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    grep_schema = [s for s in agent_tool_schemas() if s["name"] == "grep_source"][0]
    assert "regex_timeout_seconds" not in grep_schema["input_schema"]["properties"]
    out = ToolRuntime(root).dispatch("grep_source", {"pattern": "hello"})
    assert "a.txt:1:" in out


def test_g2_variant_fixed_strings_stops_reading_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path as _Path

    from regtriage.tools import grep_source

    root = tmp_path / "ws"
    root.mkdir()
    (root / "a_first.txt").write_text("needle\n" * 60, encoding="utf-8")
    for i in range(10):
        (root / f"z{i:02d}.txt").write_bytes(b"z" * 200000 + b"\n")
    reads: list[str] = []
    original = _Path.read_bytes

    def spy(self: _Path) -> bytes:
        reads.append(self.name)
        return original(self)

    monkeypatch.setattr(_Path, "read_bytes", spy)
    hits = grep_source(root, "needle", max_results=50)
    assert len(hits) == 50
    assert reads == ["a_first.txt"]


def test_g2_variant_regex_worker_hit_cap_bounded(tmp_path: Path) -> None:
    from regtriage.tools.files import _collect_candidates, _run_regex_worker
    from regtriage.tools.sandbox import resolve_within_root

    root = tmp_path / "ws"
    root.mkdir()
    (root / "m.txt").write_text("hitme\n" * 500, encoding="utf-8")
    resolved = resolve_within_root(root, ".")
    cands = _collect_candidates(resolved, resolved)
    assert len(_run_regex_worker("hitme", cands, 5.0, hit_cap=3)) == 3


def test_c1_variant_worktree_nul_rejected(tmp_path: Path) -> None:
    from regtriage.errors import ValidationError
    from regtriage.validation import Evidence, validate_evidence

    root = tmp_path / "ws"
    root.mkdir()
    (root / "blob.bin").write_bytes(b"hello\x00world\n")
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(
            root, Evidence(kind="source", ref="blob.bin", line_start=1, line_end=1, quote="hello")
        )
    assert "NUL" in str(exc_info.value)


def test_c1_variant_nul_outside_window_still_rejected(tmp_path: Path) -> None:
    if __import__("shutil").which("git") is None:
        pytest.skip("git missing")
    from regtriage.errors import ValidationError
    from regtriage.validation import Evidence, validate_evidence

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.email", "t@e"], cwd=repo, check=True, timeout=60)
    (repo / "f.v").write_text("clean line\n", encoding="utf-8")
    (repo / "blob.bin").write_bytes(b"clean line\nline\x00x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "add"],
        cwd=repo,
        check=True,
        timeout=60,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60, check=True
    ).stdout.strip()
    with pytest.raises(ValidationError):
        validate_evidence(
            repo, Evidence(kind="commit", ref=f"{sha}:blob.bin", line_start=1, line_end=1, quote="clean line")
        )


def test_d1_variant_colon_dir_denied(tmp_path: Path) -> None:
    from regtriage.errors import SandboxViolationError
    from regtriage.tools import read_log_lines
    from regtriage.tools.sandbox import denied_name_reason

    root = tmp_path / "ws"
    root.mkdir()
    (root / "ok.txt").write_text("hi\n", encoding="utf-8")
    assert denied_name_reason(Path("C:/r/sub:dir/f.v")) is not None
    with pytest.raises(SandboxViolationError) as exc_info:
        read_log_lines(root, "sub:dir/f.v")
    assert exc_info.value.violation_type == "denied_name"


def test_d1_variant_commit_rel_with_colon_denied(tmp_path: Path) -> None:
    if __import__("shutil").which("git") is None:
        pytest.skip("git missing")
    from regtriage.errors import SandboxViolationError
    from regtriage.validation import Evidence, validate_evidence

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "config", "user.email", "t@e"], cwd=repo, check=True, timeout=60)
    (repo / "a.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "add"],
        cwd=repo,
        check=True,
        timeout=60,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60, check=True
    ).stdout.strip()
    # Blocked everywhere; Windows parses `a:b.v` as ADS syntax (path_traversal),
    # POSIX resolves it inside the root (denied_name). Either verdict is safe.
    with pytest.raises(SandboxViolationError) as exc_info:
        validate_evidence(
            repo, Evidence(kind="commit", ref=f"{sha}:a:b.v", line_start=1, line_end=1, quote="x")
        )
    assert exc_info.value.violation_type in ("denied_name", "path_traversal")
