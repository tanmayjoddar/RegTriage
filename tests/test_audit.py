"""Tests for the JSONL audit logger (real files, no mocks)."""

import json
import os
from pathlib import Path

from regtriage.audit import AuditLogger


def test_append_writes_jsonl_records(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    audit = AuditLogger(log)
    audit.append("request", {"model": "m", "n": 1})
    audit.append("response", {"stop": "end_turn"})
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["kind"] for r in records] == ["request", "response"]
    assert records[0]["payload"] == {"model": "m", "n": 1}
    assert all("ts" in r and "T" in r["ts"] for r in records)


def test_creates_parent_dirs(tmp_path: Path) -> None:
    log = tmp_path / "deep" / "nested" / "audit.jsonl"
    AuditLogger(log).append("request", {})
    assert log.is_file()


def test_file_mode_is_owner_only(tmp_path: Path) -> None:
    if os.name != "posix":
        import pytest

        pytest.skip("POSIX file modes do not apply on this platform")
    log = tmp_path / "audit.jsonl"
    AuditLogger(log).append("request", {})
    assert (log.stat().st_mode & 0o777) == 0o600


def test_path_property(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    assert AuditLogger(log).path == log
