# RegTriage Run State (updated after every slice)

- Last completed slice: 4 (sandboxed tools + adversarial tests)
- What is done:
  - Slices 0, 2, 3 committed (9b65c02, 3a18ad1, 47a61f7).
  - Slice 4: `src/regtriage/tools/` (sandbox.py realpath confinement,
    files.py read_log_lines/grep_source, git.py git_blame/git_log) and
    `tests/test_tools.py` (32 tests on real files + real temp git repos,
    no mocked git/filesystem). 105 passed + 2 skipped, coverage 96.21%.
    tools/files.py 96%, tools/git.py 98%, tools/sandbox.py 100%.
  - All 5 checks green (bandit: 7 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 5 — evidence validator (`src/regtriage/validation/`
  with Evidence model {kind log|source|commit, ref, line_start, line_end,
  quote<=200 chars}; path-inside-root check, lines-exist check,
  whitespace-normalized quote-substring check, commit-sha-touched-file check;
  exact-error feedback, max 2 retries, then "unverified" with failed items
  listed, never silently drop/accept). CRITICAL: decode cited files with
  errors="replace" to match tools slice. Plus tests, 5 INTERVIEW Q&A,
  verification log entry, commit "slice 5: ...".
- Open issues:
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9. Clean Linux
    install from requirements.lock --require-hashes NOT YET RUN BY A HUMAN.
  - cocotb+Icarus integration test never executed here; real sim run on
    Linux NOT YET RUN BY A HUMAN.
  - Symlink-escape test skips on Windows (no privilege) and huge-file test
    uses 1 MB sparse + parametric cap (~387 MB free here); both need Linux
    CI for full-strength runs.
  - `runner/local.py` killpg/defensive lines need Linux CI for coverage.
  - Malformed-model-JSON adversarial case belongs to Slice 6 (agent), not
    done yet.
  - Threshold default 0.75 unevaluated on real logs; revisit with Slice 8
    harness measurements.
  - Template leftovers kept untouched and untracked (index.html,
    package.json, tsconfig.json, vite.config.ts, metadata.json, .env.example,
    requirements.txt, src/App.tsx, src/main.tsx, src/index.css). Planned
    removal in Slice 11 (explicit, not silent).
