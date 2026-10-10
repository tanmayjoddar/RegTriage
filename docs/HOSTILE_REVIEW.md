# RegTriage Hostile Review Log (Rounds 1 & 2)

This document tracks all adversarial and hostile review findings across both rounds, their attack vectors, resolution status, and proof tests.

---

## Round 1 Findings and Resolutions

### Finding 1: Read tools allowed reading `.git` internals, `.env` files, and private keys
- **Vector**: Agent could call `read_file` or `grep_source` to read `.git/config`, `.env`, `id_rsa`, leaking tokens or local git configuration.
- **Resolution**: Deny names matching `.git` (files/dirs at any depth), `.env*`, and private key suffixes (`id_rsa`, `*.pem`, etc.) in `src/regtriage/tools/files.py`.
- **Status**: FIXED (commit `76e950c`). Tested in `tests/test_hostile_regressions.py`.

### Finding 2: Commit citations did not enforce line windows against cited blob versions
- **Vector**: Model could cite arbitrary lines in a commit diff that did not correspond to the actual changed blob window.
- **Resolution**: Enforced blob-window semantics on Evidence model and checked commit citations against exact diff line ranges.
- **Status**: FIXED (commits `ce77f28`, `e9cae0c`). Tested in `tests/test_hostile_regressions.py`.

### Finding 3: Secret redaction did not cover wide enough variety of sensitive shapes
- **Vector**: AWS access keys, GitHub tokens, Slack tokens, private keys, and arbitrary key-value credentials could bypass basic pattern checks.
- **Resolution**: Widened `SecretRedactor` patterns to cover PEM blocks, AWS keys, GitHub tokens, Slack tokens, email addresses, and key-value formats.
- **Status**: FIXED (commit `f7c7353`). Tested in `tests/test_hostile_regressions.py`.

### Finding 4: Assistant echoes and tool responses were logged before redaction
- **Vector**: Raw tool responses and model echoes could enter audit logs or prompt history unscrubbed.
- **Resolution**: Scrub assistant turns and tool results at loop egress before audit logging and re-sending (`_scrub_response`).
- **Status**: FIXED (commit `6d059e1`). Tested in `tests/test_hostile_regressions.py`.

### Finding 5: Regex search could backtrack catastrophically (ReDoS) or sniff patterns
- **Vector**: Agent-supplied regex patterns could trigger exponential backtracking and hang the process.
- **Resolution**: Regex matching moved to an isolated sacrificial subprocess with hard timeout; heuristic sniffing replaced with strict child process isolation; default made literal string search (`fixed_strings=True`).
- **Status**: FIXED (commit `208f0c3`). Tested in `tests/test_hostile_regressions.py`.

### Finding 6: Subprocess git environment was not isolated
- **Vector**: Host environment variables (`GIT_DIR`, `GIT_WORK_TREE`, etc.) could hijack git subprocesses and read outside the repo.
- **Resolution**: Scrubbed all `GIT_*` environment variables, isolated user config via null device, and pinned repo discovery to root.
- **Status**: FIXED (commit `217adc1`). Tested in `tests/test_hostile_regressions.py`.

### Finding 7: Cost budget guards ran post-hoc, allowing overshoots
- **Vector**: LLM call and cost limits were checked after sending the call, allowing the budget to be exceeded.
- **Resolution**: Added pre-send budget guard in `MeteredClient` raising dedicated `BudgetExceeded` error before any over-budget send occurs.
- **Status**: FIXED (commit `1c59e5e`). Tested in `tests/test_hostile_regressions.py`.

---

## Round 2 Findings and Resolutions

### R1: Response scrubbing covered values only; dict keys and tool name/id/stop_reason leaked
- **Vector**: If a secret appeared as a dictionary key in tool input, or in a tool name, tool call ID, or stop reason, `_scrub_response` preserved it unredacted.
- **Resolution**: Extended `_scrub_response` and `_scrub_value` to recursively redact dictionary keys (`_scrub_key`), tool names, tool IDs, and stop reasons.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_r1_*`.

### R2: JSON strings with escape sequences broke naive regex key-value matching
- **Vector**: Escaped quotes inside strings (e.g. `\"`) confused regex-based pair matching, truncating or bypassing redaction.
- **Resolution**: Implemented `_scan_quoted` parser that accurately tracks backslash-escapes to find real string boundaries.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_r2_*`.

### B1: Per-arm ceilings ignored the global shared eval budget remainder
- **Vector**: In multi-arm eval runs, an arm with remaining per-arm budget could overshoot the global eval ceiling if previous arms had consumed budget.
- **Resolution**: `MeteredClient` checks the shared `_Budget` before forwarding every call, preventing joint overshoot across arms.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_b1_*`.

### G1: Model could override its own regex timeout clock
- **Vector**: Agent passing an arbitrarily large `regex_timeout_seconds` in tool arguments could cause the runner to wait indefinitely.
- **Resolution**: Hard server-side clamp on `regex_timeout_seconds` via `_MAX_REGEX_TIMEOUT_SECONDS = 5.0`.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_g1_*`.

### G2: Grep piped full corpus over stdin with no early exit
- **Vector**: Grep tool buffered the entire repository into memory and sent it over stdin to the child process even when max results were reached.
- **Resolution**: Implemented streaming generator `_iter_candidates` with early exit on hit cap, and bounded total scanned bytes by `_MAX_TOTAL_SCAN_BYTES = 2_000_000`.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_g2_*`.

### D1: Windows NTFS Alternate Data Streams (ADS) bypassed file name matching
- **Vector**: Accessing `file.txt:stream` on Windows could bypass denied name checks like `.env` or read hidden stream data.
- **Resolution**: Added colon/stream checks in `_is_denied_name` to reject Alternate Data Stream paths.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_d1_*`.

### C1: Binary files containing NUL bytes but valid UTF-8 were citable in evidence
- **Vector**: Evidence validator accepted files containing NUL bytes if they decoded as valid UTF-8, whereas read tools skip binary files.
- **Resolution**: Evidence validator checks for NUL bytes (`b"\0"` in first 8192 bytes) matching read-tool binary detection.
- **Status**: FIXED (commit `c9104b9`). Tested in `tests/test_hostile_regressions_r2.py::test_c1_*`.

### R3: Base64-wrapped and line-wrapped secrets
- **Vector**: High-entropy strings split across lines or base64-encoded do not match regex shape patterns.
- **Resolution**: Documented as an acknowledged inherent limitation in `docs/THREAT_MODEL.md` ("What redaction still cannot catch"). Redaction is a safety net for accidental cleartext leakage, not a general DLP system. Egress control relies on append-only audit logging and `--offline` flag.
- **Status**: DOCUMENTED KNOWN LIMITATION.
