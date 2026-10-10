# RegTriage Run State (updated after every slice)

- Last completed slice: 8 (eval harness, baseline, three arms, cost guard,
  results, CLI)
- What is done:
  - Slices 0, 2-7 committed; CI green incl. matrix --require-hashes jobs.
  - Slice 8: `src/regtriage/eval/` (upstream pin 25156a9a/MIT verified,
    6 seeded operators, scoring, harness with baseline gate + 3 arms +
    budgets, results I/O + manual timing), `src/regtriage/cli.py` (run,
    report, eval, eval-report, validate-config; fixes Slice-1 entry point),
    `eval/manual_triage.csv` (header-only template).
  - 209 passed + 4 skipped, coverage 97.83%; eval/* ≥96%.
    All 5 checks green (bandit: 9 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 9 — SlurmExecutor + systemd + infra docs. New:
  `src/regtriage/runner/slurm.py` (Executor Protocol; sbatch --parsable,
  poll sacct/squeue, scancel on timeout, batch script from template),
  `deploy/regtriage.service` + `regtriage.timer` + Slurm batch template,
  `docs/INFRA.md` (single-node Slurm VM + NFS export, exact verification
  commands, all NOT YET RUN BY A HUMAN). Slurm tests against fake
  sbatch/squeue/sacct/scancel shims on PATH. +5 INTERVIEW Q&A; log entry;
  commit "slice 9: ...". (Polish here is cut candidate #3 if forced.)
- Open issues:
  - Live Anthropic calls NEVER made; forced-submit quality unmarked.
  - Real eval (baseline green + 30 mutants + 3 arms) NEVER run — needs
    Linux + Icarus + cocotb + API key. First on RUNBOOK list.
  - Manual timing CSV has zero rows (template only — honest, no numbers).
  - Skips: "iverilog not installed", "cannot create symlinks on this
    machine", "POSIX file modes do not apply on this platform",
    make-gated simulate test (runs on Linux CI).
  - RUNBOOK.md lands in Slice 11; until then human-only items live here.
  - `.pre-commit-config.yaml` with detect-secrets hook still to write
    (Slice 11).
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9.
  - Threshold default 0.75 still unevaluated (needs real eval numbers).
  - Template leftovers kept untouched and untracked. Planned removal in
    Slice 11 (explicit, not silent).
