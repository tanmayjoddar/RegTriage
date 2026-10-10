# RegTriage Run State (updated after every slice)

- Last completed slice: 9 (SlurmExecutor + systemd + infra docs)
- What is done:
  - Slices 0, 2-8 committed; CI green incl. matrix --require-hashes jobs.
  - Slice 9: `src/regtriage/runner/slurm.py` (sbatch --parsable, poll,
    scancel, template) + `tests/test_runner_slurm.py` (3 portable + 7
    POSIX-shim tests, skipped here, run on Linux CI) + `deploy/` units +
    `docs/INFRA.md` (all commands NOT YET RUN BY A HUMAN).
  - 212 passed + 11 skipped, coverage 95.01% (slurm.py full on Linux).
    All 5 checks green (bandit: 11 justified nosecs); log + INTERVIEW done.
- Exact next step: Slice 10 — UVM + Verilator parsers (cut candidate #1
  if budget forces it, but it is small: mirror the cocotb parser).
  New: `src/regtriage/parsing/uvm.py` (UVM_ERROR/UVM_FATAL),
  `src/regtriage/parsing/verilator.py` (%Warning/%Error),
  `tests/fixtures/uvm*.log + verilator*.log`, `tests/test_parsing_extra.py`.
  +5 INTERVIEW Q&A; log entry; commit "slice 10: ...".
  Then Slice 11 (README/RUNBOOK/THREAT_MODEL/RESULTS stub, remove template
  leftovers explicitly), then mandatory final self-audit +
  docs/COMPLETION_REPORT.md.
- Open issues:
  - Live Anthropic calls NEVER made; forced-submit quality unmarked.
  - Real eval NEVER run (needs Linux + Icarus + cocotb + key).
  - Manual timing CSV has zero rows (honest template).
  - Platform-gated skips (iverilog, symlinks, POSIX modes, make, slurm
    shims) run on Linux CI; this box covers the portable subset.
  - RUNBOOK.md lands in Slice 11; human-only items live here till then.
  - Threshold 0.75 unevaluated (needs real eval numbers).
  - Template leftovers kept untouched and untracked. Planned removal in
    Slice 11 (explicit, not silent).
