# RegTriage Run State (updated after every slice)

- Last completed slice: 5 (evidence validator + tests)
- Remote: https://github.com/tanmayjoddar/RegTriage.git (branch master,
  pushed 2026-10-10). History rewritten once before first push so all
  commits carry tanmayjoddar <tanmayjoddar17@gmail.com>; hashes below are
  post-rewrite.
- What is done:
  - Slices 0, 2, 3, 4 committed (e51b79e, 1de80f0, a5d2701, 22e06e8).
  - Slice 5: `src/regtriage/validation/` (Evidence model, normalize_quote,
    validate_evidence with exact-reason errors, commit sha/touched/diff
    checks) and `tests/test_validation.py` (19 tests, real files + real
    temp git). Promoted tools.git `_run_git` to public `run_git`.
  - 124 passed + 2 skipped, coverage 96.15%, validation/* at 95-100%.
    All 5 checks green (bandit: 7 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 6 — agent loop, ReplayClient, AnthropicClient,
  redaction on egress, audit log, injection tests. New: `src/regtriage/agent/`
  (LLM client Protocol + AnthropicClient + ReplayClient via DI; tool-use loop
  max 8 calls/cluster, token + call ceilings from config, graceful abort;
  final answer ONLY via submit_diagnosis with Diagnosis schema; force with
  tool_choice at step cap; tool errors as is_error results), Diagnosis model
  {cluster_id, root_cause_summary<=400, suspected_files, evidence[],
  confidence 0-1, next_steps<=3, status verified|unverified|failed},
  `src/regtriage/audit.py` (append-only JSONL, mode 0600, --offline/--dry-run
  logs without sending), redaction applied to EVERYTHING sent to the LLM,
  untrusted-data delimiters + data-not-instructions system prompt,
  malformed-model-JSON adversarial test. Tests use ReplayClient; +5
  INTERVIEW Q&A; log entry; commit "slice 6: ...".
- Open issues:
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9. Clean Linux
    install from requirements.lock --require-hashes NOT YET RUN BY A HUMAN.
  - cocotb+Icarus integration test never executed here; real sim run on
    Linux NOT YET RUN BY A HUMAN. Real Anthropic calls never made here.
  - Symlink-escape test skips on Windows; huge-file test parametric;
    validator read-race (42-43) + malformed-record (git.py 135) guards
    uncovered — all need Linux CI / adversarial review.
  - Threshold default 0.75 unevaluated on real logs; revisit with Slice 8.
  - Template leftovers kept untouched and untracked. Planned removal in
    Slice 11 (explicit, not silent).
