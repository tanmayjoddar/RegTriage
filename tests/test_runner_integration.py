"""Slow integration test: a real cocotb + Icarus regression via LocalExecutor.

Skips with a printed reason when Icarus Verilog or cocotb is not installed.
"""

import importlib.util
import shutil
from pathlib import Path

import pytest

from regtriage.parsing import CocotbResultsParser
from regtriage.runner import JobSpec, LocalExecutor

pytestmark = pytest.mark.slow

_DUT_PASS = """\
module tiny_and (
    input wire a,
    input wire b,
    output wire y
);
assign y = a & b;
endmodule
"""

_DUT_BROKEN = """\
module tiny_and (
    input wire a,
    input wire b,
    output wire y
);
assign y = a | b;
endmodule
"""

_COCOTB_TEST = """\
import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_and_gate(dut: object) -> None:
    assert dut is not None
    for a in (0, 1):
        for b in (0, 1):
            dut.a.value = a  # type: ignore[attr-defined]
            dut.b.value = b  # type: ignore[attr-defined]
            await Timer(1, unit="ns")
            got = int(dut.y.value)  # type: ignore[attr-defined]
            assert got == (a & b), f"a={a} b={b} y={got}"
"""

_MAKEFILE = """\
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(CURDIR)/tiny_and.v
TOPLEVEL = tiny_and
MODULE = test_tiny
include $(shell cocotb-config --makefiles)/Makefile.sim
"""


def _write_project(root: Path, dut_source: str) -> None:
    """Write a minimal DUT, cocotb test module, and GNU Makefile."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "tiny_and.v").write_text(dut_source, encoding="utf-8")
    (root / "test_tiny.py").write_text(_COCOTB_TEST, encoding="utf-8")
    (root / "Makefile").write_text(_MAKEFILE, encoding="utf-8")


def test_cocotb_regression_with_icarus(tmp_path: Path) -> None:
    """Run a real two-job regression: green DUT passes, broken DUT fails."""
    if shutil.which("iverilog") is None:
        print("SKIP: iverilog not found on PATH; cannot run real cocotb regression")
        pytest.skip("iverilog not installed")
    if shutil.which("cocotb-config") is None:
        print("SKIP: cocotb-config not found on PATH; cannot run cocotb makefile")
        pytest.skip("cocotb build scripts not installed")
    if shutil.which("make") is None:
        print("SKIP: make not found on PATH; cannot drive cocotb regression")
        pytest.skip("make not installed")
    if importlib.util.find_spec("cocotb") is None:
        print("SKIP: cocotb package not importable; cannot run real cocotb test")
        pytest.skip("cocotb not installed")

    executor = LocalExecutor(max_parallel=1, default_timeout_seconds=300.0)
    parser = CocotbResultsParser()

    green = tmp_path / "green"
    _write_project(green, _DUT_PASS)
    (green_result,) = executor.run_jobs([JobSpec(job_id="sim-green", argv=["make"], cwd=green)])
    assert green_result.timed_out is False
    assert green_result.returncode == 0, green_result.stdout[-2000:]
    assert parser.parse(green / "results.xml") == []

    red = tmp_path / "red"
    _write_project(red, _DUT_BROKEN)
    (red_result,) = executor.run_jobs([JobSpec(job_id="sim-red", argv=["make"], cwd=red)])
    assert red_result.timed_out is False
    failures = parser.parse(red / "results.xml")
    assert len(failures) >= 1
    assert all(f.message != "" for f in failures)
