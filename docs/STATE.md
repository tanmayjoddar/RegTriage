# RegTriage Run State (updated after every slice)

- Last completed: hostile review response — all 7 findings fixed, one
  commit each (1c59e5e, f7c7353, 6d059e1, 208f0c3, 217adc1, ce77f28,
  76e950c), plus evidence-docstring fix (e9cae0c).
- What is done: `tests/test_hostile_regressions.py` (46 tests: probes shown
  RED pre-fix + variants); BudgetExceeded pre-send guard; widened redaction;
  response/echo scrubbing with exact-egress audit; fixed-string grep +
  killable regex child (sniffing deleted); GIT_* scrub + config isolation
  (NOSYSTEM deviation documented); blob-window commit citations + bytes-core
  git runner; denied names (.git/.env/keys). 264 passed + 11 skipped
  (Windows, 94.68%), 274 + 1 (WSL Linux). All 5 checks green.
  COMPLETION_REPORT rows E6/M6/M8/M9/C4 corrected to PARTIALLY-then-FIXED;
  THREAT_MODEL updated incl. "what redaction cannot catch"; INTERVIEW +5.
- Exact next step: push docs + poll CI to green, then final summary to user.
  Human-only backlog unchanged (RUNBOOK): toolchain, baseline, API key,
  eval numbers, manual timing, Slurm/NFS/systemd, secrets audit.
