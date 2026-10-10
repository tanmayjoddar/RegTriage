# RegTriage threat model

## Trust zones

| Zone | Trust | Examples |
| --- | --- | --- |
| Operator config, CLI flags (non-secret), own source | Trusted | `pyproject.toml`, checked-in code |
| Environment secrets | Trusted but fragile | `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `SLACK_WEBHOOK_URL` (see handling) |
| Sim logs, RTL source, testbenches | UNTRUSTED | `results.xml`, `*.log`, `*.v`, cocotb output |
| Upstream checkout under test | UNTRUSTED | `verilog-pcie` working copies, mutant cases |
| Model output | UNTRUSTED | tool calls, submitted diagnoses, quotes |
| Git history of case copies | Sanitized | single squashed commit only (eval) |

## Threats and mitigations

1. **Prompt injection via logs/source.** Sim output may contain instructions
   ("ignore previous instructions..."). Mitigations: every tool result is
   wrapped in `<untrusted-data>` blocks; the system prompt states block
   content is data, never instructions; tools never interpret file contents
   (tested: injection text round-trips as inert data).
2. **Path escape (`..`, absolute paths, symlink swaps).** All tool and
   validator paths resolve against the allowed root via `realpath` and are
   rejected outside it (tested, incl. symlink and `..` cases). Residual
   TOCTOU risk documented in INTERVIEW slice 4.
3. **Secret-bearing paths (new).** `.git` internals (file or directory, any
   depth — worktree pointers included), `.env`/`.env.*` files, and private
   key names/suffixes (`id_rsa`, `*.pem`, ...) are denied in direct reads
   (loud `denied_name`) and skipped silently in grep walks. Ordinary
   dotfiles stay readable (pinned by test, including `.pub` keys).
3. **ReDoS via agent-supplied regex.** Regex is opt-in only
   (`fixed_strings=False`); the default is literal substring search, which
   cannot backtrack by construction. Opt-in patterns compile and match in a
   sacrificial child process killed after a hard timeout (`regex_timeout`;
   all-or-nothing per call, no partial results). Pattern-length caps remain;
   shape-sniffing heuristics were tried, disproved by review, and deleted.
4. **Secret leakage to the LLM or logs.** `SecretRedactor` scrubs everything
   sent to the model: Anthropic + AWS + GitHub + Slack keys, JWTs, bearer
   tokens, PEM blocks, key=value secrets, quoted JSON pairs, "password is"
   phrases, emails. Model responses and assistant echoes are scrubbed
   before audit logging and before re-sending (tools execute with original
   arguments; validation uses the original submission). API keys travel as
   `SecretStr` from environment only, never in argv, reports, or audit
   payloads; audit log is 0600 and stores redacted-as-sent payloads, so it
   shows exactly what left the machine. `detect-secrets` runs in pre-commit
   with a committed baseline (8 known-fake fixtures recorded; run
   `detect-secrets audit .secrets.baseline` before `pre-commit install`).
5. **Malicious XML (entity expansion).** `results.xml` parsing rejects any
   `<!DOCTYPE` before `ElementTree` (defusedxml is outside the dependency
   budget) under a 32 MB cap.
6. **Ground-truth leakage in eval.** Mutants run on temp copies; case dirs
   are neutral (`case-NNNN`); the tree is re-inited as one squashed commit
   so blame/log carry no signal; no mutant metadata in paths, env, prompts,
   or agent-visible logs (tested).
7. **Git subprocess environment.** Every git child runs with all `GIT_*`
   scrubbed (demonstrated hijack: `GIT_DIR`+`GIT_WORK_TREE` decoy → fatal
   "outside repository"), the user global config replaced by the null
   device, and discovery ceiling-pinned to the root. Two deliberate
   omissions, empirically grounded: `GIT_CONFIG_NOSYSTEM` is not set and
   conversion is not pinned, because disabling both collapses
   Git-for-Windows blame to all-zero SHAs while shared-environment
   writes/reads always agree (9 experiments in the verification log).
   Git output decoding is explicit UTF-8 (bytes-cored runner), never
   locale-dependent.
7. **Supply chain.** Hashed `requirements.lock` (82 packages/entries, all release
   files), minimal runtime deps (anthropic, google-genai, pydantic, typer), pinned CI
   actions (commit SHAs), `pip-audit` in CI (clean, 0 known vulnerabilities).
8. **Markdown/report injection.** All untrusted report text is
   backslash-escaped; JSON relies on `json.dumps` structure; Slack webhook
   URL is https-allowlisted and never appears in errors.
9. **Provider-specific data privacy and retention.**
   - **Gemini Free-Tier Data Use**: When using the Google Gemini API with a free-tier API key, Google's Terms of Service permit prompts and responses to be stored, reviewed by human reviewers, and used to train or improve Google models and products. For proprietary RTL repositories, operators MUST either use a Paid Google Gemini Tier (where inputs/outputs are not used to train models) or configure `--offline` mode.
   - **True Egress Control vs Safety Net**: Regex redaction (`SecretRedactor`) is inherently a best-effort defense-in-depth safety net against accidental cleartext credential leakage; it is NOT a cryptographic or complete Data Loss Prevention (DLP) boundary. The true egress controls are:
     1. Append-only, unbuffered `audit.jsonl` (mode 0600 on POSIX) capturing every exact byte sequence emitted to the network for independent operator inspection.
     2. `--offline` / `ReplayClient` flag which guarantees zero network sockets are opened to any external API provider.

## Out of scope

Model obedience is assumed, not enforced: a model that follows embedded
instructions despite the system prompt is not stopped by any mechanism here
(the validator checks citations, not obedience). Side-channel, Slurm
controller, and NFS server threats are the operator's (see INFRA.md).

## What redaction still cannot catch (hostile-review residual)

Regex redaction is shape-matching, and shapes are enumerable while secrets
are not. Known blind spots, each pinned or documented:
- **Bare high-entropy tokens** with no marker (`hunter2...` alone on a
  line, raw hex API tokens): no pattern fires. This is the largest residual;
  entropy-based detection was rejected as a dependency/scope expansion.
- **Split/obfuscated secrets**: tokens broken across lines, URL-encoded,
  base64-wrapped, or concatenated (`"sk" + "-ant-..."`) never match.
- **Novel vendor prefixes**: any scheme not in the pattern list (new AI
  vendors, internal `COMPANY-...` tokens) passes until a pattern is added.
  The list is reviewed per finding, not proactively.
- **Secrets inside tool arguments**: scrubbed in echoes/audit, but tools
  execute with originals — a grep pattern containing a live secret still
  runs locally (results are redacted on return).
- **Over-redaction**: `password is ...` and JSON-pair rules can mangle
  innocent prose ("the password is strong" loses "strong"); treatment is
  fail-closed by design.
- **`.env.*` collateral**: `.env.example`-style safe templates are denied
  alongside real `.env` files (closed-by-default, documented).
Redaction remains a safety net for accidental leaks, not a DLP guarantee:
least-privilege scopes and ephemeral credentials are the real controls.
