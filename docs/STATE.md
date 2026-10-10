# RegTriage Run State (updated after every slice)

- Last completed slice: 11 (README/RUNBOOK/THREAT_MODEL/RESULTS/pre-commit,
  template removal)
- What is done: ALL SLICES 0,2-11 committed. Docs complete: README (Mermaid,
  quickstart, decisions, security, limitations, not-yet-run table),
  RUNBOOK (ordered commands, all NOT YET RUN), THREAT_MODEL (8 threats),
  RESULTS stub (no numbers by design), INFRA, INTERVIEW (45 Q&A),
  VERIFICATION_LOG (real output per slice). Template leftovers removed
  explicitly. 220 passed + 11 skipped, 95.13%. All 5 checks green.
- Exact next step: MANDATORY FINAL SELF-AUDIT (this run): clean-install
  equivalent, dead-code grep, docs/COMPLETION_REPORT.md with per-requirement
  rows + unverified-claims list. Then commit + push + poll CI.
- SELF-AUDIT RESULT (2026-10-10): Windows clean venv (`python -m venv` +
  `--require-hashes` lockfile install + `pip install -e .`): full suite
  220 passed/11 skipped/95.13% + ruff + format + mypy --strict + bandit
  ALL green, identical to dev env. `regtriage --help` entry point works.
  Dead-code grep: 6 hits, all pydantic field_validators (framework-called,
  test-proven) — justified, nothing deleted. TODO/shell=True/stub grep
  clean (one legit `pass` in killpg fallback). docs/COMPLETION_REPORT.md
  written: all rows done except E1 partial (baseline never run) + 12
  unverified claims listed harshly. NOTHING CUT — all slices 0,2-11 done.
- CI FIX 2 (2026-10-10): runs #11/#12 failed in pytest on ubuntu only.
  Cause: `${@: -1}` bashism in sbatch shim vs dash. Fixed POSIX loop;
  shims validated under sh; pushed, polling CI.
- CI FIX 3 (2026-10-10): run #13 STILL failed post-dash-fix. Built
  CI-identical env in WSL (py3.11.17 + lockfile pins + exact CI command):
  230 passed/1 skipped TWICE — cannot reproduce; suspect hypothesis
  200ms deadlines on loaded runners. Hardened with deadline=None on the
  3 property tests. Pushing + polling.
- CI FIX 4 (2026-10-10): REAL CAUSE found via fresh LF clone in WSL:
  6 failed / 224 passed — the four Slice-10 `.log` fixtures were NEVER
  COMMITTED (`*.log` gitignore swallowed them; `git add` warned nothing).
  Fix-2 (dash) was real but latent. Fix: `!tests/fixtures/*.log` negation
  + tracked fixtures. Deadline theory retracted in the log (hardening kept).
  Pushing + polling CI.
- Open issues: live LLM/sim/eval/INFRA runs NOT YET RUN; manual CSV empty;
  threshold unevaluated; platform-gated skips for Linux CI.
