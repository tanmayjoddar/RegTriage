"""Pinned upstream regression target: repo, commit, license, eval modules.

Verified 2026-10-10 via the GitHub API: alexforencich/verilog-pcie is
MIT-licensed (SPDX MIT) — it is NOT the successor project "taxi"
(CERN-OHL-S/commercial), which this project must not use. The pin below is
the master HEAD as of that date. The baseline MUST run green on a real
toolchain before any mutation; the harness aborts otherwise.
"""

UPSTREAM_URL = "https://github.com/alexforencich/verilog-pcie.git"
UPSTREAM_PIN = "25156a9a162c41c60f11f41590c7d006d015ae5a"
UPSTREAM_PIN_DATE = "2024-04-26"
UPSTREAM_LICENSE_SPDX = "MIT"

# Candidate small testbenches (tb dirs) and their DUTs (rtl files), all
# confirmed present at UPSTREAM_PIN. Confirm each goes green with the
# RUNBOOK baseline command before trusting eval numbers.
EVAL_MODULES: tuple[str, ...] = (
    "tb/dma_psdpram",
    "tb/irq_rate_limit",
    "tb/dma_if_axi",
)
EVAL_TARGETS: tuple[str, ...] = (
    "rtl/dma_psdpram.v",
    "rtl/irq_rate_limit.v",
    "rtl/dma_if_axi.v",
)
