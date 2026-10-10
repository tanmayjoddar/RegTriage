# RegTriage Run State (updated after every slice)

- Last completed slice: 7 (reports + Slack + escaping)
- What is done:
  - Slices 0, 2-6 committed; CI fix + matrix job green (runs #3-5 success,
    ubuntu AND windows, incl. --require-hashes installs).
  - Slice 7: `src/regtriage/report/` (escape_markdown, build_json_report,
    render_markdown, send_slack with https/loopback allowlist) and
    `tests/test_report.py` (13 tests incl. localhost webhook stub).
  - 171 passed + 3 skipped, coverage 97.43%; report/* at 100%.
    All 5 checks green (bandit: 8 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 8 — eval harness (NEVER CUT). New: `eval/`
  package (mutants, baseline, three arms, cost guard, results generator),
  `src/regtriage/cli.py` (typer: run, report, eval, eval-report,
  validate-config — CLI was listed in MODULES but assigned no slice; it
  lands here where all subsystems exist), `eval/manual_triage.csv` +
  timing script, generated `eval/results.json` + `docs/RESULTS.md`.
  Requires choosing the pinned verilog-pcie commit SHA + verifying its
  LICENSE (MIT-style, NOT taxi/CERN-OHL-S) — web research + RUNBOOK note.
  +5 INTERVIEW Q&A; log entry; commit "slice 8: ...".
- Open issues:
  - Live Anthropic calls NEVER made; forced-submit quality unmarked.
  - Slack `<!here>`-style mentions not neutralized; no webhook retry.
  - Proxy env vars could break localhost Slack tests (no no_proxy guard).
  - `.pre-commit-config.yaml` with detect-secrets hook still to write
    (Slice 11 with docs).
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9.
  - cocotb+Icarus integration never executed; real sim on Linux NOT YET
    RUN BY A HUMAN. Skips: "iverilog not installed",
    "cannot create symlinks on this machine",
    "POSIX file modes do not apply on this platform".
  - RUNBOOK.md lands in Slice 11; until then human-only items live here.
  - Threshold default 0.75 unevaluated on real logs; Slice 8 measures it.
  - Template leftovers kept untouched and untracked. Planned removal in
    Slice 11 (explicit, not silent).
