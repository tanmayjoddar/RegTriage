"""Unit tests for the cocotb JUnit results.xml parser."""

from pathlib import Path

import pytest

from regtriage.errors import ConfigurationError, ParsingError
from regtriage.parsing import CocotbResultsParser

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_passing_results_yield_no_failures() -> None:
    parser = CocotbResultsParser()
    assert parser.parse(FIXTURES / "cocotb_pass.xml") == []


def test_failing_results_yield_one_failure_per_broken_case() -> None:
    parser = CocotbResultsParser()
    failures = parser.parse(FIXTURES / "cocotb_fail.xml")
    assert len(failures) == 2

    by_test = {f.test: f for f in failures}
    dma = by_test["test_pcie_dma::test_dma_len"]
    assert "0x40001000" in dma.message
    assert "0xDEAD" in dma.raw_excerpt
    assert dma.log_path == FIXTURES / "cocotb_fail.xml"
    assert dma.line is None

    msi = by_test["test_pcie_msi::test_msi_irq"]
    assert "simulator exited" in msi.message
    assert msi.raw_excerpt != ""


def test_empty_testsuite_yields_no_failures() -> None:
    parser = CocotbResultsParser()
    assert parser.parse(FIXTURES / "cocotb_empty.xml") == []


def test_missing_file_raises_parsing_error() -> None:
    parser = CocotbResultsParser()
    with pytest.raises(ParsingError) as exc_info:
        parser.parse(FIXTURES / "does-not-exist.xml")
    assert exc_info.value.source_path is not None


def test_directory_path_raises_parsing_error(tmp_path: Path) -> None:
    parser = CocotbResultsParser()
    with pytest.raises(ParsingError):
        parser.parse(tmp_path)


def test_malformed_xml_raises_parsing_error(tmp_path: Path) -> None:
    bad = tmp_path / "results.xml"
    bad.write_text('<testsuite><testcase name="oops"', encoding="utf-8")
    with pytest.raises(ParsingError):
        CocotbResultsParser().parse(bad)


def test_invalid_utf8_raises_parsing_error(tmp_path: Path) -> None:
    bad = tmp_path / "results.xml"
    bad.write_bytes(b"\xff\xfe<testsuite><testcase /></testsuite>")
    with pytest.raises(ParsingError):
        CocotbResultsParser().parse(bad)


def test_oversized_file_raises_parsing_error() -> None:
    parser = CocotbResultsParser(max_bytes=10)
    with pytest.raises(ParsingError):
        parser.parse(FIXTURES / "cocotb_pass.xml")


def test_bare_failure_without_message_or_text(tmp_path: Path) -> None:
    bare = tmp_path / "results.xml"
    bare.write_text(
        '<?xml version="1.0"?><testsuite><testcase><failure /></testcase></testsuite>',
        encoding="utf-8",
    )
    (failure,) = CocotbResultsParser().parse(bare)
    assert failure.test == "unknown"
    assert failure.message == "failure"
    assert failure.raw_excerpt == ""


def test_excerpt_is_capped(tmp_path: Path) -> None:
    big = tmp_path / "results.xml"
    big.write_text(
        '<?xml version="1.0"?>'
        '<testsuite><testcase classname="c" name="n">'
        f'<failure message="boom">{"y" * 5000}</failure>'
        "</testcase></testsuite>",
        encoding="utf-8",
    )
    (failure,) = CocotbResultsParser(max_excerpt_chars=100).parse(big)
    assert len(failure.raw_excerpt) == 100


def test_doctype_declaration_is_rejected(tmp_path: Path) -> None:
    evil = tmp_path / "results.xml"
    evil.write_text(
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lollollol">]>'
        '<testsuite><testcase classname="c" name="n" /></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ParsingError):
        CocotbResultsParser().parse(evil)


def test_invalid_constructor_args_rejected() -> None:
    with pytest.raises(ConfigurationError):
        CocotbResultsParser(max_bytes=0)
    with pytest.raises(ConfigurationError):
        CocotbResultsParser(max_excerpt_chars=0)
