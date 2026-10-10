# RegTriage Run State (updated after every slice)

- Last completed slice: 2 (LocalExecutor + cocotb results parsing + real
  integration test)
- What is done:
  - Slice 0 committed (9b65c02): model default `claude-sonnet-5-5`, nosec
    B105 justification, pinned CI SHAs, conftest uses DEFAULT_MODEL_ID.
  - Slice 2: `src/regtriage/runner/` (Executor Protocol, JobSpec/JobResult,
    LocalExecutor with bounded parallelism, per-job timeout, process-group
    kill, 200k output cap) and `src/regtriage/parsing/` (Parser Protocol,
    Failure, CocotbResultsParser with UTF-8/malformed/size/DOCTYPE guards).
  - Tests: 12 LocalExecutor unit tests (real subprocesses), 12 parser unit
    tests, 1 slow integration test (real cocotb+Icarus, skips with printed
    reason here), 3 XML fixtures. 59 passed + 1 skipped, coverage 95.37%.
  - `slow` marker registered in pyproject.toml. Bandit clean with 5 justified
    nosecs (B105/B314/B405/B404/B603). All 5 checks green; real output in
    docs/VERIFICATION_LOG.md; +5 Q&A in docs/INTERVIEW.md.
- Exact next step: Slice 3 — signature normalization + clustering
  (`src/regtriage/signature.py`: normalize hex/numbers/timestamps/paths/
  instance indices, hash, cluster identical, Jaccard merge above threshold)
  with hypothesis property tests (idempotent, order-independent), 5 INTERVIEW
  Q&A, verification log entry, commit "slice 3: ...".
- Open issues:
  - `.venv/` in the repo is Linux-only; verification on this Windows box used
    system Python 3.11.9. Clean Linux install from requirements.lock with
    --require-hashes NOT YET RUN BY A HUMAN.
  - Integration test has never executed (no iverilog/cocotb here); real sim
    run on Linux NOT YET RUN BY A HUMAN.
  - `runner/local.py` lines 30-36 (killpg), 46/72/82 (defensive fallbacks)
    uncovered on Windows; killpg branch needs Linux CI to cover.
  - Template leftovers kept untouched and untracked: index.html,
    package.json, tsconfig.json, vite.config.ts, metadata.json, .env.example,
    requirements.txt, src/App.tsx, src/main.tsx, src/index.css. Planned
    removal in Slice 11 (explicit, not silent).
