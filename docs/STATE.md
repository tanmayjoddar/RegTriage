# RegTriage Run State (updated after every slice)

- Last completed slice: 10 (UVM + Verilator parsers + fixtures + tests)
- What is done:
  - Slices 0, 2-9 committed; CI green incl. matrix --require-hashes jobs.
  - Slice 10: `src/regtriage/parsing/` +logs.py/uvm.py/verilator.py,
    4 fixtures, `tests/test_parsing_extra.py` (8 tests). uvm/verilator
    100%, logs 92% (read-race guard, same class as validator 42-43).
  - 220 passed + 11 skipped, coverage 95.13%. All 5 checks green
    (bandit: 11 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 11 (last feature slice) — README, RUNBOOK,
  THREAT_MODEL, generated RESULTS stub + template removal. Work:
  1. `README.md`: Mermaid diagram, quickstart, design decisions, security
     model, limitations, results table generated from eval/results.json
     ("not yet run" if absent — it IS absent; generate, do not hand-write).
     Small generator: reuse render_results_markdown? README table needs its
     own snippet — write `scripts/`? NO new deps; inline python in docs?
     Simplest honest: README contains a static "not yet run" table now +
     documents the `eval-report` regeneration command. No fabricated numbers.
  2. `docs/RUNBOOK.md`: ordered exact commands (install Icarus, clone+pin,
     API key, run eval, manual timing, Slurm/NFS, systemd units).
  3. `docs/THREAT_MODEL.md`: untrusted logs/source, prompt injection,
     delimiters, redaction, secret handling, mutant isolation.
  4. `docs/RESULTS.md`: generate via eval-report from ABSENT results.json?
     Cannot — write the stub manually stating "not yet run" + limitations
     (this is the specified stub behavior, not fabricated results).
  5. `.pre-commit-config.yaml` (detect-secrets hook) — required by hard rules.
  6. Remove template leftovers EXPLICITLY (list in commit message + here):
     index.html, package.json, tsconfig.json, vite.config.ts, metadata.json,
     .env.example, requirements.txt, src/App.tsx, src/main.tsx,
     src/index.css. Keep: src/regtriage.egg-info? Remove too (build artifact).
     Keep .venv? It is gitignored... .venv is NOT tracked (gitignored? check:
     .gitignore has .venv/ — yes added slice 0). Leave on disk, untracked.
  7. +5 INTERVIEW Q&A; log entry; commit "slice 11: ...".
- Then: MANDATORY final self-audit (clean venv install from lockfile —
  impossible on this Windows box with Linux hashes; do closest equivalent +
  record honestly; dead-code grep; docs/COMPLETION_REPORT.md with per-row
  proof + unverified-claims list; short COMPLETION_REPORT even if cut).
- Open issues: (same as before +) live LLM/sim/eval/INFRA runs all
  NOT YET RUN BY A HUMAN; manual CSV empty; threshold unevaluated.
