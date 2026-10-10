# RegTriage threat model

## Trust zones

| Zone | Trust | Examples |
| --- | --- | --- |
| Operator config, CLI flags (non-secret), own source | Trusted | `pyproject.toml`, checked-in code |
| Environment secrets | Trusted but fragile | `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL` (see handling) |
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
3. **ReDoS via agent-supplied regex.** Static rejection of nested-quantifier
   and quantified-alternation shapes + length cap + bounded haystack. No
   preemptive timeout exists in stdlib `re` (documented limitation).
4. **Secret leakage to the LLM or logs.** `SecretRedactor` scrubs everything
   sent to the model (keys, bearer tokens, PEM blocks, key=value secrets,
   emails); API key travels as `SecretStr` from environment only, never in
   argv, reports, or audit payloads; audit log is 0600 and stores
   redacted-as-sent payloads. `detect-secrets` runs in pre-commit with a
   committed baseline (8 known-fake fixtures recorded; run
   `detect-secrets audit .secrets.baseline` before `pre-commit install`).
5. **Malicious XML (entity expansion).** `results.xml` parsing rejects any
   `<!DOCTYPE` before `ElementTree` (defusedxml is outside the dependency
   budget) under a 32 MB cap.
6. **Ground-truth leakage in eval.** Mutants run on temp copies; case dirs
   are neutral (`case-NNNN`); the tree is re-inited as one squashed commit
   so blame/log carry no signal; no mutant metadata in paths, env, prompts,
   or agent-visible logs (tested).
7. **Supply chain.** Hashed `requirements.lock` (70 entries, all release
   files), minimal runtime deps (anthropic, pydantic, typer), pinned CI
   actions (commit SHAs), `pip-audit` in CI (currently clean).
8. **Markdown/report injection.** All untrusted report text is
   backslash-escaped; JSON relies on `json.dumps` structure; Slack webhook
   URL is https-allowlisted and never appears in errors.

## Out of scope

Model obedience is assumed, not enforced: a model that follows embedded
instructions despite the system prompt is not stopped by any mechanism here
(the validator checks citations, not obedience). Side-channel, Slurm
controller, and NFS server threats are the operator's (see INFRA.md).
