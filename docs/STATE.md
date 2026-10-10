# RegTriage Run State (updated after every slice)

- Current task: Task 2e - Re-verify default Gemini model ID against current docs (config-only).
- Done:
  - Slices 0-11 per `docs/COMPLETION_REPORT.md`.
  - Hostile review round 1 (7 fixes committed).
  - Hostile review round 2 fixes (R1, R2, B1, G1, G2, C1, D1; committed in c9104b9).
  - Task 1: GeminiClient initial wiring and retry-hint error detail fix (committed in b0c7e77).
  - Task 2a: Tool-call id collisions fixed with per-client counter / UUID fallback at response time (committed in 1ba29ec).
  - Task 2b: Cost accounting: config-driven `ModelPriceEstimate` per provider and model, labeled as estimates, fail loudly on unpriced models with `ConfigurationError` (committed in 7dc723b).
  - Task 2c: Message roles: function responses translated with role="user" with function_response part and id, matching official Gemini API & SDK specifications (committed in 919b1bb).
  - Task 2d: Thought signatures: opaque `provider_state` on `ToolUseBlock` & `TextBlock` (excluded from audit dump via `exclude=True`), unmangled by redaction, captured in `_from_gemini_response`, echoed on function calls in `_to_gemini_contents`.
- In progress / Next steps (in order per brief):
  2. Fix suspected defects:
     e. Re-verify default Gemini model ID against current docs (config-only).
     f. Grep tests for vacuous assertions and remove; prove `test_gemini_triage_redaction_and_audit_parity` non-vacuous.
  3. Replace `test_live_gemini_tiny_prompt` with opt-in live test (2-turn round trip).
  4. Regenerate hash-pinned `requirements.lock` including `google-genai` and run `pip-audit`.
  5. Update docs (`THREAT_MODEL.md`, `README.md`, `HOSTILE_REVIEW.md`, `VERIFICATION_LOG.md`, `COMPLETION_REPORT.md`).
  6. Final checks: ruff check, ruff format --check, mypy --strict, pytest --cov --cov-branch, bandit, pip-audit; push and confirm CI green.
