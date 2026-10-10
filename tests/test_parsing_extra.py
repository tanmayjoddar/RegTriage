"""Tests for the UVM and Verilator lint parsers (sample fixtures)."""

from pathlib import Path

import pytest

from regtriage.errors import ConfigurationError, ParsingError
from regtriage.parsing import UvmLogParser, VerilatorLintParser, read_log_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_uvm_pass_has_no_failures() -> None:
    assert UvmLogParser().parse(FIXTURES / "uvm_pass.log") == []


def test_uvm_fail_lines_parsed() -> None:
    failures = UvmLogParser().parse(FIXTURES / "uvm_fail.log")
    assert len(failures) == 2
    error, fatal = failures
    assert error.test == "uvm_error"
    assert error.line == 3
    assert "0x40001000" in error.message
    assert error.log_path == FIXTURES / "uvm_fail.log"
    assert fatal.test == "uvm_fatal"
    assert fatal.line == 5
    assert "MSI-X" in fatal.message


def test_uvm_ignores_info_lines() -> None:
    assert all("UVM_INFO" not in f.message for f in UvmLogParser().parse(FIXTURES / "uvm_fail.log"))


def test_verilator_pass_has_no_failures() -> None:
    assert VerilatorLintParser().parse(FIXTURES / "verilator_pass.log") == []


def test_verilator_fail_lines_parsed() -> None:
    failures = VerilatorLintParser().parse(FIXTURES / "verilator_fail.log")
    assert len(failures) == 3
    kinds = [f.test for f in failures]
    assert kinds == ["verilator_warning", "verilator_warning", "verilator_error"]
    assert failures[0].line == 2
    assert "UNUSEDSIGNAL" in failures[0].message
    assert "WIDTH" in failures[1].message
    assert failures[2].line == 4


def test_log_parsers_reject_bad_inputs(tmp_path: Path) -> None:
    for parser in (UvmLogParser(), VerilatorLintParser()):
        with pytest.raises(ParsingError):
            parser.parse(tmp_path / "ghost.log")
        with pytest.raises(ParsingError):
            parser.parse(tmp_path)
    bad = tmp_path / "odd.log"
    bad.write_bytes(b"\xff\xfe binary")
    for parser in (UvmLogParser(), VerilatorLintParser()):
        with pytest.raises(ParsingError):
            parser.parse(bad)
    big = tmp_path / "big.log"
    big.write_text("UVM_ERROR x\n", encoding="utf-8")
    with pytest.raises(ParsingError):
        UvmLogParser(max_bytes=5).parse(big)


def test_log_parsers_reject_bad_limits() -> None:
    with pytest.raises(ConfigurationError):
        UvmLogParser(max_bytes=0)
    with pytest.raises(ConfigurationError):
        UvmLogParser(max_excerpt_chars=0)
    with pytest.raises(ConfigurationError):
        VerilatorLintParser(max_bytes=0)
    with pytest.raises(ConfigurationError):
        VerilatorLintParser(max_excerpt_chars=0)
    with pytest.raises(ConfigurationError):
        read_log_text(FIXTURES / "uvm_pass.log", max_bytes=0)


def test_read_log_text_returns_lines() -> None:
    lines = read_log_text(FIXTURES / "uvm_pass.log")
    assert len(lines) == 3
    assert lines[1].startswith("UVM_INFO")
