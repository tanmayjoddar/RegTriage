"""Tests for the machine-checked evidence validator (real files, real git)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from regtriage.errors import SandboxViolationError, ValidationError
from regtriage.validation import Evidence, normalize_quote, validate_evidence

GIT = shutil.which("git")


def _reason(exc_info: pytest.ExceptionInfo[ValidationError]) -> str:
    """Unwrap the optional reason field for membership assertions."""
    reason = exc_info.value.reason
    assert reason is not None
    return reason


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Directory with a sim log and an RTL source file."""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "sim.log").write_text(
        "0.00ns: reset deasserted\n"
        "1.00ns: UVM_ERROR   dma length   mismatch at 0x40001000\n"
        "2.00ns: test ends\n",
        encoding="utf-8",
    )
    rtl = root / "rtl"
    rtl.mkdir()
    (rtl / "pcie_dma.v").write_text(
        "module pcie_dma;\n  reg [31:0] len;\n  // dma length check\nendmodule\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Real git repo: commit 1 adds a file, commit 2 appends a line."""
    if GIT is None:
        pytest.skip("git not installed: cannot build temp git repo")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Validator Tester")
    _git(repo, "config", "user.email", "validator@example.com")
    src = repo / "rtl" / "pcie_dma.v"
    src.parent.mkdir(parents=True)
    src.write_text("module pcie_dma;\nendmodule\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add dma module")
    src.write_text("module pcie_dma;\n  reg [31:0] len;\nendmodule\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add len register")
    return repo


def _sha(repo: Path, rev: str) -> str:
    return _git(repo, "rev-parse", rev).strip()


def test_valid_log_citation(workdir: Path) -> None:
    evidence = Evidence(
        kind="log",
        ref="sim.log",
        line_start=2,
        line_end=2,
        quote="UVM_ERROR dma length mismatch at 0x40001000",
    )
    validate_evidence(workdir, evidence)


def test_valid_source_citation_multi_line(workdir: Path) -> None:
    evidence = Evidence(
        kind="source",
        ref="rtl/pcie_dma.v",
        line_start=1,
        line_end=3,
        quote="reg [31:0] len;",
    )
    validate_evidence(workdir, evidence)


def test_quote_mismatch_reports_exact_error(workdir: Path) -> None:
    evidence = Evidence(
        kind="log", ref="sim.log", line_start=2, line_end=2, quote="all green, no errors"
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(workdir, evidence)
    err = exc_info.value
    assert err.citation_kind == "log"
    assert err.citation_ref == "sim.log"
    assert "not found" in _reason(exc_info)
    assert "sim.log" in str(err) and "2-2" in str(err)


def test_wrong_case_quote_fails(workdir: Path) -> None:
    evidence = Evidence(kind="log", ref="sim.log", line_start=2, line_end=2, quote="uvm_error dma")
    with pytest.raises(ValidationError):
        validate_evidence(workdir, evidence)


def test_empty_quote_rejected(workdir: Path) -> None:
    evidence = Evidence(kind="log", ref="sim.log", line_start=1, line_end=1, quote="   ")
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(workdir, evidence)
    assert "empty" in _reason(exc_info)


def test_lines_beyond_eof_rejected(workdir: Path) -> None:
    evidence = Evidence(kind="log", ref="sim.log", line_start=2, line_end=99, quote="x")
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(workdir, evidence)
    assert "exceed" in _reason(exc_info)


def test_reversed_range_rejected(workdir: Path) -> None:
    evidence = Evidence(kind="log", ref="sim.log", line_start=3, line_end=2, quote="x")
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(workdir, evidence)
    assert "before" in _reason(exc_info)


def test_missing_file_rejected(workdir: Path) -> None:
    evidence = Evidence(kind="log", ref="ghost.log", line_start=1, line_end=1, quote="x")
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(workdir, evidence)
    assert "not a file" in _reason(exc_info)


def test_escape_is_sandbox_violation_not_validation_error(workdir: Path) -> None:
    evidence = Evidence(kind="source", ref="../outside.v", line_start=1, line_end=1, quote="x")
    with pytest.raises(SandboxViolationError):
        validate_evidence(workdir, evidence)


def test_quote_length_capped_by_schema() -> None:
    with pytest.raises(PydanticValidationError):
        Evidence(kind="log", ref="a.log", line_start=1, line_end=1, quote="y" * 201)
    ok = Evidence(kind="log", ref="a.log", line_start=1, line_end=1, quote="y" * 200)
    assert len(ok.quote) == 200


def test_invalid_kind_rejected_by_schema() -> None:
    with pytest.raises(PydanticValidationError):
        Evidence(kind="email", ref="a.log", line_start=1, line_end=1, quote="x")  # type: ignore[arg-type]


def test_replace_decoding_matches_tools(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "odd.log").write_bytes(b"bad \xff\xfe bytes\n")
    evidence = Evidence(kind="log", ref="odd.log", line_start=1, line_end=1, quote="bad")
    validate_evidence(root, evidence)


def test_normalize_quote_collapses_whitespace() -> None:
    assert normalize_quote("  a\t\n  b  ") == "a b"
    assert normalize_quote("") == ""


def test_valid_commit_citation(git_repo: Path) -> None:
    sha = _sha(git_repo, "HEAD")
    evidence = Evidence(
        kind="commit",
        ref=f"{sha}:rtl/pcie_dma.v",
        line_start=1,
        line_end=1,
        quote="reg [31:0] len;",
    )
    validate_evidence(git_repo, evidence)


def test_commit_sha_must_exist(git_repo: Path) -> None:
    evidence = Evidence(
        kind="commit",
        ref=f"{'0' * 40}:rtl/pcie_dma.v",
        line_start=1,
        line_end=1,
        quote="len",
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(git_repo, evidence)
    assert "does not exist" in _reason(exc_info)


def test_commit_must_touch_cited_file(git_repo: Path) -> None:
    first = _sha(git_repo, "HEAD~1")
    evidence = Evidence(
        kind="commit",
        ref=f"{first}:rtl/unrelated.v",
        line_start=1,
        line_end=1,
        quote="whatever",
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(git_repo, evidence)
    assert "did not touch" in _reason(exc_info)


def test_commit_quote_must_appear_in_diff(git_repo: Path) -> None:
    sha = _sha(git_repo, "HEAD")
    evidence = Evidence(
        kind="commit",
        ref=f"{sha}:rtl/pcie_dma.v",
        line_start=1,
        line_end=1,
        quote="something never in the diff",
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_evidence(git_repo, evidence)
    assert "not found" in _reason(exc_info)


def test_commit_malformed_refs_rejected(git_repo: Path) -> None:
    for bad in ("not-a-ref", "short:rtl/pcie_dma.v", f"{'g' * 40}:rtl/pcie_dma.v"):
        evidence = Evidence(kind="commit", ref=bad, line_start=1, line_end=1, quote="x")
        with pytest.raises(ValidationError) as exc_info:
            validate_evidence(git_repo, evidence)
        assert "must look like" in _reason(exc_info)


def test_commit_path_escape_rejected(git_repo: Path) -> None:
    sha = _sha(git_repo, "HEAD")
    evidence = Evidence(
        kind="commit", ref=f"{sha}:../escape.v", line_start=1, line_end=1, quote="x"
    )
    with pytest.raises(SandboxViolationError):
        validate_evidence(git_repo, evidence)
