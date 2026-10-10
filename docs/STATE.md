# RegTriage Run State (updated after every slice)

- Current task: Task 6 - Final checks suite (ruff check, ruff format --check, mypy --strict, pytest --cov --cov-branch, bandit, pip-audit), push, and confirm CI green.
- Done:
  - Slices 0-11 per `docs/COMPLETION_REPORT.md`.
  - Hostile review round 1 (7 fixes committed).
  - Hostile review round 2 fixes (R1, R2, B1, G1, G2, C1, D1; committed in c9104b9).
  - Task 1: GeminiClient initial wiring and retry-hint error detail fix (committed in b0c7e77).
  - Task 2a: Tool-call id collisions fixed with per-client counter / UUID fallback at response time (committed in 1ba29ec).
  - Task 2b: Cost accounting: config-driven `ModelPriceEstimate` per provider and model, labeled as estimates, fail loudly on unpriced models with `ConfigurationError` (committed in 7dc723b).
  - Task 2c: Message roles: function responses translated with role="user" with function_response part and id, matching official Gemini API & SDK specifications (committed in 919b1bb).
  - Task 2d: Thought signatures: opaque `provider_state` on `ToolUseBlock` & `TextBlock` (excluded from audit dump via `exclude=True`), unmangled by redaction, captured in `_from_gemini_response`, echoed on function calls in `_to_gemini_contents` (committed in 851232a).
  - Task 2e: Re-verified default Gemini model ID `gemini-3.8-flash` against official models docs; config-only.
  - Task 2f: Grepped tests for vacuous assertions (none found); proved `test_gemini_triage_redaction_and_audit_parity` non-vacuous by temporarily disabling redaction and showing failure.
  - Task 3: Replaced `test_live_gemini_tiny_prompt` with opt-in `test_live_gemini_two_turn_tool_call` (2-turn round trip). Listed in `docs/RUNBOOK.md` as NOT YET RUN BY A HUMAN (committed in 51c06d1).
  - Task 4: Regenerated hash-pinned `requirements.lock` including `google-genai` and complete transitive closure (82 packages, hashes from PyPI for all platforms); ran `pip-audit` (`No known vulnerabilities found`); verified clean venv install with `pip install --require-hashes -r requirements.lock`.
  - Task 5: Docs updated: `THREAT_MODEL.md` (Gemini free-tier data policy, audit log and --offline as real egress controls, 82 lockfile packages, GEMINI_API_KEY in trust zones), `README.md` (provider selection, env vars, honest limits, 82 packages), `HOSTILE_REVIEW.md` (both rounds, all findings and status), `VERIFICATION_LOG.md` (real outputs for r2 regressions, Gemini suite, pip-audit, clean venv install, Research Rules external citations), `COMPLETION_REPORT.md` (updated S4 to 82 packages, T5 to Gemini, nosec B311 justification on backoff jitter, unverified claims list updated with live Gemini).
- In progress / Next steps (in order per brief):
  6. Final checks: ruff check, ruff format --check, mypy --strict, pytest --cov --cov-branch, bandit, pip-audit on clean venv; push; confirm CI is green.

