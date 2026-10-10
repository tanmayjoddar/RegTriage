"""Tests for the typer CLI (CliRunner, no network, offline paths are real)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from regtriage.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_validate_config_ok(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate-config"], env={"REGTRIAGE_MODEL": "m"})
    assert result.exit_code == 0, result.output
    assert '"model_id": "m"' in result.output
    assert "ANTHROPIC_API_KEY" not in result.output


def test_validate_config_masks_secrets(clean_env: pytest.MonkeyPatch) -> None:
    result = runner.invoke(
        app, ["validate-config"], env={"ANTHROPIC_API_KEY": "sk-ant-secretkey1234567890"}
    )
    assert result.exit_code == 0, result.output
    assert "sk-ant-secretkey1234567890" not in result.output
    assert "[MASKED_KEY]" in result.output


def test_validate_config_rejects_bad_env(clean_env: pytest.MonkeyPatch) -> None:
    result = runner.invoke(app, ["validate-config"], env={"REGTRIAGE_MAX_STEPS": "0"})
    assert result.exit_code == 2


def test_report_regenerates_markdown(tmp_path: Path) -> None:
    payload = {
        "generated_at": "t",
        "model_id": "m",
        "cluster_count": 1,
        "clusters": [
            {"cluster_id": "c1", "signature": "s", "members": [{"test": "t", "message": "# hi"}]}
        ],
        "diagnoses": {
            "c1": {
                "root_cause_summary": "x",
                "status": "verified",
                "confidence": 1.0,
                "next_steps": [],
            }
        },
        "status_counts": {"verified": 1, "unverified": 0, "failed": 0},
    }
    src = tmp_path / "run.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "r.md"
    result = runner.invoke(app, ["report", "--report-json", str(src), "--out-md", str(out)])
    assert result.exit_code == 0, result.output
    assert "\\# hi" in out.read_text(encoding="utf-8")


def test_run_with_key_and_no_clusters(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "o"
    result = runner.invoke(
        app,
        [
            "run",
            "--repo",
            str(repo),
            "--results-xml",
            str(FIXTURES / "cocotb_pass.xml"),
            "--out",
            str(out),
        ],
        env={"ANTHROPIC_API_KEY": "sk-ant-unusedkey"},
    )
    assert result.exit_code == 0, result.output
    assert "clusters=0" in result.output


def test_run_posts_to_slack_stub(
    clean_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from typing import Any as _Any

    received: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            received.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: _Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/hook"
        monkeypatch.setenv("SLACK_WEBHOOK_URL", url)
        repo = tmp_path / "repo"
        repo.mkdir()
        result = runner.invoke(
            app,
            [
                "run",
                "--repo",
                str(repo),
                "--results-xml",
                str(FIXTURES / "cocotb_pass.xml"),
                "--out",
                str(tmp_path / "o"),
                "--offline",
                "--slack",
            ],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    assert result.exit_code == 0, result.output
    assert _json.loads(received[0])["text"].startswith("# RegTriage report")


def test_report_rejects_non_object(tmp_path: Path) -> None:
    src = tmp_path / "arr.json"
    src.write_text("[1, 2]", encoding="utf-8")
    result = runner.invoke(app, ["report", "--report-json", str(src)])
    assert result.exit_code == 2


def test_eval_missing_repo_is_exit_1(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "eval",
            "--repo",
            str(tmp_path / "nope"),
            "--work",
            str(tmp_path / "work"),
            "--mutants",
            "1",
            "--out",
            str(tmp_path / "r.json"),
            "--offline",
        ],
    )
    assert result.exit_code == 1


def test_make_eval_client_branches() -> None:
    from pydantic import SecretStr as _SecretStr

    from regtriage.agent import AnthropicClient as _Live
    from regtriage.agent import ReplayClient as _Replay
    from regtriage.cli import _make_eval_client

    assert isinstance(_make_eval_client(True, None), _Replay)
    assert isinstance(_make_eval_client(False, None), _Replay)
    assert isinstance(_make_eval_client(False, _SecretStr("k")), _Live)


def test_report_rejects_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    result = runner.invoke(app, ["report", "--report-json", str(bad)])
    assert result.exit_code == 2


def test_run_offline_end_to_end(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fixture = FIXTURES / "cocotb_fail.xml"
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["run", "--repo", str(repo), "--results-xml", str(fixture), "--out", str(out), "--offline"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "run.json").is_file()
    assert (out / "report.md").is_file()
    assert "clusters=2" in result.output and "failed=2" in result.output


def test_run_needs_key_or_offline(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = runner.invoke(
        app,
        [
            "run",
            "--repo",
            str(repo),
            "--results-xml",
            str(FIXTURES / "cocotb_pass.xml"),
            "--out",
            str(tmp_path / "o"),
        ],
    )
    assert result.exit_code == 2


def test_slack_without_url_fails(
    clean_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    result = runner.invoke(
        app,
        [
            "run",
            "--repo",
            str(repo),
            "--results-xml",
            str(FIXTURES / "cocotb_pass.xml"),
            "--out",
            str(tmp_path / "o"),
            "--offline",
            "--slack",
        ],
    )
    assert result.exit_code == 2


def test_eval_aborts_on_red_baseline(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "dummy.v").write_text("module dummy;\nendmodule\n", encoding="utf-8")
    out = tmp_path / "eval" / "results.json"
    result = runner.invoke(
        app,
        [
            "eval",
            "--repo",
            str(repo),
            "--work",
            str(tmp_path / "work"),
            "--mutants",
            "1",
            "--out",
            str(out),
            "--offline",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "aborted=True" in result.output
    assert out.is_file()


def test_eval_report_renders_results(tmp_path: Path) -> None:
    results = {
        "pin": "abc",
        "seed": 0,
        "modules": ["m"],
        "target_files": ["f"],
        "baseline": [{"module": "m", "passed": True, "failure_count": 0}],
        "generated": 1,
        "killed": 1,
        "used": 1,
        "arms": {
            "full": {
                "arm": "full",
                "hit_file": 1.0,
                "hit_module": 1.0,
                "hit_line": 0.0,
                "fab_before": 0.0,
                "fab_after": 0.0,
                "used": 1,
            }
        },
        "cost": {"llm_calls": 1, "input_tokens": 0, "output_tokens": 0, "usd": 0.0},
        "mean_agent_seconds": 2.0,
        "aborted": False,
        "abort_reason": "",
    }
    src = tmp_path / "results.json"
    src.write_text(json.dumps(results), encoding="utf-8")
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "case_id,file,operator,manual_seconds,notes\nm0000,f.v,flip,62.0,\n", encoding="utf-8"
    )
    out = tmp_path / "RESULTS.md"
    result = runner.invoke(
        app,
        ["eval-report", "--results", str(src), "--out-md", str(out), "--manual-csv", str(manual)],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "simpler than" in text and "Manual triage mean" in text


def test_eval_report_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["eval-report", "--results", str(tmp_path / "no.json")])
    assert result.exit_code == 2
