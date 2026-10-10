# RegTriage Technical Interview Companion

This document records architectural decisions, defense rationale, and honest discussions of design limitations across each slice of RegTriage.

---

## Slice 1: Foundation, Tooling, Config, Logging, Errors, CI Skeleton

### 1. Why do you enforce `SecretStr` in Pydantic and restrict secrets strictly to environment variables instead of accepting CLI flags or checked-in config files?
**Answer:**
In enterprise hardware verification farms (Slurm clusters, Jenkins/GitLab runners, LSF compute nodes), command-line arguments are readable by any local user or monitoring daemon via `/proc/<pid>/cmdline` and `ps -ef`. Similarly, configuration files in shared NFS scratch disks often have permissive umasks (e.g., `0644`), risking credential exposure across engineering teams, or risk accidental git commits.

By binding secrets strictly to environment variables (`ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL`) and wrapping them immediately into Pydantic's `SecretStr`, secrets are never displayed in `repr()`, string formatting, or standard `model_dump()` serialization. Furthermore, our `mask_for_logging()` explicitly sanitizes configuration dumps before telemetry or stdout logging.

**Limitation:**
Environment variables are not completely invulnerable; on Linux machines without `hidepid` mounted on `/proc`, another process running as the same UID can read `/proc/<pid>/environ`. For full production hardening, credentials must be supplied via restricted file descriptors or systemd `EnvironmentFile` with mode `0600`, which we integrate in Slice 9.

---

### 2. Why did you create an explicit exception hierarchy (`RegTriageError`) with structured payload dictionaries rather than using standard Python exceptions or string messages?
**Answer:**
Automated regression triage operates across five distinct operational domains:
1. Environment and parameter setup (`ConfigurationError`)
2. Subprocess execution, EDA simulation crashes, and job timeouts (`ExecutionError`)
3. Simulation artifact, XML, or log parsing defects (`ParsingError`)
4. Filesystem path traversal or resource boundary escapes (`SandboxViolationError`)
5. LLM agent evidence citation discrepancies (`ValidationError`)
6. Agent token/step budget limits (`AgentLoopError`)

Using standard exceptions like `ValueError` or `RuntimeError` forces callers and CLI handlers to rely on brittle string inspection to distinguish between a malformed XML log and a path traversal attack. Structured exception objects carry typed metadata (`returncode`, `command`, `parameter_name`, `citation_kind`, `timed_out`) that downstream reporters and audit loggers can serialize into structured machine-readable error records via `to_dict()`.

**Limitation:**
Adding metadata to exception payloads requires discipline to ensure that untrusted inputs (e.g., multi-megabyte log excerpts) or sensitive tokens are truncated and redacted before being attached to exception payloads, preventing memory bloat or credential leaks in traceback dumps.

---

### 3. What are the failure modes and security limitations of your regex-based `SecretRedactor` in `logging.py`?
**Answer:**
The `SecretRedactor` provides defense-in-depth sanitization for stdout and structured JSON logs by applying compiled regular expressions against known token shapes:
- Anthropic API keys (`sk-ant-[a-zA-Z0-9_\-]{20,}`)
- Bearer tokens (`Bearer <base64/jwt>`)
- PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----`)
- Generic assignment patterns (`api_key=...`, `token=...`)
- Email addresses

**Failure modes and limitations:**
1. **High-entropy token false negatives:** Secrets generated without recognizable prefixes or standard key-value assignments (for example, raw 32-character hexadecimal API tokens in arbitrary log output) will bypass regex filters unless matched by entropy analysis.
2. **Obfuscation evasion:** If an attacker or untrusted simulation output splits a token across multiple lines, inserts URL-encoding (`%20`), or base64-encodes the credential, regex matching will not trigger.
3. **ReDoS risk:** Complex regular expressions on unbounded log strings can cause catastrophic backtracking. We maintain strictly linear, unnested regex patterns to guarantee $O(n)$ scanning time.

Regex redaction is a safety net against accidental leaks, not a substitute for least-privilege credential scopes and ephemeral token issuance.

---

### 4. Why did you choose `ConfigDict(frozen=True, extra='forbid')` for `RegTriageConfig`, and what performance/architectural tradeoffs does this introduce?
**Answer:**
PCIe regression triage runs are deterministic multi-step pipelines. Once initialized from CLI flags and environment variables, configuration parameters (such as `workspace_root`, `timeout_seconds`, `model_id`, `token_ceiling`) must be immutable:
- `frozen=True` guarantees that no downstream agent step, executor callback, or tool helper can mutate global configuration state mid-run, eliminating concurrency bugs.
- `extra='forbid'` ensures that misconfigured environment overrides or misspelled CLI options fail fast at launch rather than being silently ignored.

**Tradeoffs:**
- Immutability requires explicitly constructing new instances or using `model_copy(update=...)` if dynamic parameters need adjustment (e.g., in test fixtures).
- Pydantic v2 schema compilation and validation introduces microsecond-level overhead on startup compared to raw dataclasses, but this cost is entirely negligible compared to hardware simulation runtimes (seconds to hours).

---

### 5. Why enforce a lockfile with SHA-256 hashes (`requirements.lock`) and strictly constrain dependencies to `anthropic`, `pydantic>=2`, and `typer`?
**Answer:**
PCIe controller IP is critical high-value silicon design property. Verification environments often execute on internal compute networks with access to proprietary RTL codebases. Introducing untrusted third-party dependencies from PyPI introduces significant supply chain risk (dependency confusion, malicious wheel replacement, compromised maintainer accounts).

By enforcing:
1. Pinned versions with exact SHA-256 wheel and sdist hashes in `requirements.lock` (`pip install --require-hashes`)
2. A minimal dependency footprint restricted to:
   - `pydantic>=2`: boundary validation and strict type safety
   - `typer`: CLI entrypoints
   - `anthropic`: official SDK for Anthropic Messages API
   - Dev tools: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `mypy`, `bandit`

We ensure that every package in the dependency graph has been audited, that builds are completely reproducible across developer workstations and Slurm cluster nodes, and that malicious upstream package substitutions are rejected by hash verification.

**Limitation:**
Generating multi-platform hash lockfiles requires querying PyPI release digests for all platform-specific binary wheels (Linux x86_64, aarch64, macOS) when dependencies contain compiled C extensions (e.g., `pydantic-core`).

---

## Slice 0: Audit and fix (model default, nosec justification, pinned CI actions)

### 1. Why is `claude-sonnet-5-5` the default model, and how do you know it is current?
**Answer:**
I checked Anthropic's models overview page (`https://platform.claude.com/docs/en/about-claude/models/overview`) on 2026-10-10: the current Sonnet line is Claude Sonnet 5.5 with Claude API model ID `claude-sonnet-5-5`, while Sonnet 5 is marked legacy. The old default (`claude-3-7-sonnet-20250219`) was two major generations stale. The exact source URL and check date are recorded in a comment above `DEFAULT_MODEL_ID` so the next person can re-verify in seconds.

**Limitation:**
Model IDs rot quickly; a hardcoded default is stale the moment Anthropic ships the next Sonnet. The mitigation is the `REGTRIAGE_MODEL` environment override (kept), so operators can pin a new ID without a code change, plus the dated comment that makes staleness visible.

### 2. Why does `src/` contain exactly one model ID string, and why do the tests still mention another one?
**Answer:**
`DEFAULT_MODEL_ID` in `src/regtriage/config.py` is the single source of truth; `tests/conftest.py` imports it instead of repeating the string, so a model bump touches one line. `tests/test_config.py` still contains `claude-3-5-sonnet-20241022`, but only as arbitrary input data for the `REGTRIAGE_MODEL` override path — the test is meaningless unless the override value differs from the default, so any well-formed non-default string works there.

**Limitation:**
A reviewer could still mistake the test string for a supported default. If Anthropic retires that ID, nothing breaks (the override path never calls the API in unit tests), but the test data becomes misleading. A comment at the test call site says it is arbitrary input, not a supported model.

### 3. What does the `# nosec B105` in `logging.py` mean, and why keep it instead of removing it?
**Answer:**
Bandit rule B105 (`hardcoded_password_string`) fires on any string literal assigned to a variable whose name contains words like `secret`, `password`, or `token`. `_SECRET_PLACEHOLDER = "[REDACTED_SECRET]"` matches that pattern, but the string is a redaction placeholder, not a credential — there is nothing secret about the literal text `[REDACTED_SECRET]`. Removing the `nosec` would make bandit fail the build on a false positive; keeping it with the exact rule ID plus the reason documents that a human evaluated this specific finding and concluded it is not a real secret.

**Limitation:**
`nosec` suppressions are blanket trust: if someone later edits that line to hold a real secret, bandit stays silent. The defense is code review (the justification comment forces the next editor to read it) and `detect-secrets` in pre-commit, which scans for real high-entropy credentials independently of bandit.

### 4. Why pin GitHub Actions to full commit SHAs instead of `actions/checkout@v4`?
**Answer:**
A major-version tag like `@v4` is mutable: whoever controls the `actions/checkout` repo can move it at any time, so two CI runs weeks apart can execute different code with no diff in our repo. Pinning `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` (with the `# v4.2.2` comment) makes the workflow hermetic — the exact bytes CI runs are visible in our diff and can only change via an explicit commit. The SHAs were resolved through the GitHub API (`git/ref/tags/v4.2.2`, `git/ref/tags/v5.6.0`).

**Limitation:**
SHA pinning freezes us in time: we no longer receive upstream security fixes automatically (e.g., a checkout action patch for a CVE). The tradeoff is deliberate for an IP-sensitive hardware project — updates become explicit, reviewable dependency bumps — but it requires someone to run Dependabot or manually re-pin, otherwise the actions quietly age out.

### 5. The `.venv/` shipped in the ZIP is a Linux venv but you verified on Windows — is your green build trustworthy?
**Answer:**
Mostly, but with a caveat I state openly. The shipped `.venv/` (`bin/`, `lib/python3.11`) cannot execute on this Windows machine, so I ran the five checks on system Python 3.11.9 with the same tool versions (`ruff 0.17.0`, `mypy 2.4.0`, `pytest 9.1.1`) plus `pip install -e .`, and recorded the real output in `docs/VERIFICATION_LOG.md`. The application code is pure Python with no platform-specific branches, and all 35 tests plus lint/type/security checks pass, so logic correctness carries over.

**Limitation:**
I have NOT verified a clean install from `requirements.lock` with `--require-hashes` (the lockfile's hashes are Linux-wheel oriented and this machine is Windows), nor run CI on Linux. Both are listed as NOT YET RUN BY A HUMAN until someone executes the RUNBOOK commands on the target platform.
