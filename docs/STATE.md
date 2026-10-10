# RegTriage Run State (updated after every slice)

- Last completed slice: 3 (signature normalization + clustering + property
  tests)
- What is done:
  - Slices 0, 2 committed (9b65c02, 3a18ad1).
  - Slice 3: `src/regtriage/signature.py` (ordered regex normalization,
    sha256 signatures, Jaccard, exact clustering + greedy merge, frozen
    Cluster model) and `tests/test_signature.py` (12 unit + 3 hypothesis
    property tests). signature.py 100% branch-covered; total 95.95%,
    74 passed + 1 skipped. All 5 checks green; log + INTERVIEW updated.
- Exact next step: Slice 4 — sandboxed read-only tools (`src/regtriage/tools/`
  with read_log_lines, grep_source, git_blame, git_log; allowed-root
  realpath confinement, caps, regex timeout) plus ALL adversarial tests
  (prompt-injection log, symlink escape, ../ traversal, ReDoS pattern, 1 GB
  log, malformed XML, invalid UTF-8, malformed model JSON, oversized tool
  output), 5 INTERVIEW Q&A, verification log entry, commit "slice 4: ...".
- Open issues:
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9. Clean Linux
    install from requirements.lock --require-hashes NOT YET RUN BY A HUMAN.
  - cocotb+Icarus integration test never executed here; real sim run on
    Linux NOT YET RUN BY A HUMAN.
  - `runner/local.py` killpg/defensive lines need Linux CI for coverage.
  - Threshold default 0.75 unevaluated on real logs; revisit with Slice 8
    harness measurements.
  - Template leftovers kept untouched and untracked (index.html,
    package.json, tsconfig.json, vite.config.ts, metadata.json, .env.example,
    requirements.txt, src/App.tsx, src/main.tsx, src/index.css). Planned
    removal in Slice 11 (explicit, not silent).
