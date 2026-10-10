# RegTriage completion report (self-audit, 2026-10-10)

Harsh grading: done means built, tested, green locally AND on Linux CI.
"Needs human" means no run exists anywhere yet.

## Per-requirement verdicts

| # | Requirement | Verdict | Proof (file + test) |
| --- | --- | --- | --- |
| 0a | Current Sonnet default, override kept, single source | done | `src/regtriage/config.py` (`claude-sonnet-5-5`, verified 2026-10-10); `tests/test_config.py` |
| 0b | `#nosec` justified with exact rule + reason | done | 11 nosecs, each `Bxxx: reason`; `bandit` clean |
| 0c | CI actions pinned to SHAs | done | `.github/workflows/ci.yml` (checkout@11bd7190, setup-python@a26af69b); CI green |
| S1 | No stubs/TODOs/pass/NotImplemented | done | `git grep -n "TODO\|FIXME\|NotImplementedError\|pass$" src` — see notes |
| S2 | 5 checks per slice + commit + real log | done | `docs/VERIFICATION_LOG.md` (11 sections); one commit per slice |
| S3 | No fabricated metrics; scripts generate tables | done | README/RESULTS show "not yet run"; `eval/manual_triage.csv` header-only |
| S4 | Deps: anthropic/pydantic/typer + dev set + hashed lock | done | `pyproject.toml`, `requirements.lock` (70 entries); clean `--require-hashes` install verified |
| S5 | 5 interview Q&A per slice | done | `docs/INTERVIEW.md` (45 Q&A across slices 0-11) |
| T1 | Python 3.11+, src layout, strict types, lint, format | done | `mypy --strict` + `ruff` clean on 57 files, CI too |
| T2 | pydantic v2 boundaries, small fns, no globals/mutables | done | frozen models everywhere; reviewable |
| T3 | Custom exceptions from errors.py | done | `src/regtriage/errors.py`; no other exception classes defined |
| T4 | pathlib only; subprocess argv-only + timeouts | done | `git grep shell=True src` empty; every Popen/run/urlopen has timeout |
| T5 | LLM client Protocol + Anthropic + Replay (DI) | done | `src/regtriage/agent/`; `tests/test_agent.py` (31 tests) |
| M1 | LocalExecutor (parallel bound, timeout, group kill) | done | `runner/local.py`; 12 real-subprocess tests |
| M2 | SlurmExecutor (parsable, poll, scancel, template) | done | `runner/slurm.py`; shim tests run on Linux CI |
| M3 | Collect results.xml + logs + exit codes | done | `JobResult` + `CocotbResultsParser`; integration test (skipped here) |
| M4 | 3 parsers + fixtures → Failure(...) | done | `parsing/` + 4 cocotb + 4 UVM/Verilator fixtures |
| M5 | Normalize/hash/cluster/Jaccard + property tests | done | `signature.py` 100%; hypothesis idempotent/order-independent |
| M6 | 4 read-only tools, confinement, caps, regex guard, no shell | done | `tools/`; 32 adversarial-heavy tests on real files/git |
| M7 | Agent loop: 8 calls, ceilings, forced submit, is_error, Diagnosis schema | done | `agent/loop.py` 100%; budgets/retries/force all tested |
| M8 | Evidence validator + exact feedback + 2 retries → unverified | done | `validation/`; 19 tests incl. commit citations |
| M9 | Redaction on ALL LLM egress | done | loop choke point; secret-fixture tests incl. audit file |
| M10 | Audit JSONL 0600 + offline/dry-run | done | `audit.py` 100% (mode assert POSIX-gated) |
| M11 | JSON+MD reports escaped + Slack (env URL, timeout) | done | `report/` 100%; localhost-stub Slack tests |
| M12 | CLI run/report/eval/eval-report/validate-config | done | `cli.py` 99%; CliRunner tests incl. offline e2e |
| C1 | Threat model doc | done | `docs/THREAT_MODEL.md` |
| C2 | Untrusted-data blocks + data-not-instructions prompt | done | `SYSTEM_PROMPT`; injection round-trip tests |
| C3 | Adversarial tests (all 9 listed) | done | injection✓, symlink✓*, ../✓, ReDoS✓, 1GB✓ parametric, malformed XML✓, bad UTF-8✓, bad model JSON✓, oversized output✓ (*POSIX-gated here) |
| C4 | Secrets: env-only, redaction, temp copies, detect-secrets, bandit+pip-audit | done | SecretStr env loading; `.secrets.baseline` committed (audit pending); CI runs both |
| T6 | ReplayClient units + slow integration + real git + shims + ≥90% | done | 95.13% total, branch coverage, Linux CI runs gated tests |
| E1 | 3-5 small modules, green baseline gate | partial | modules/targets named from verified API listing, but baseline NEVER run → gate untested live |
| E2 | 6 operators, ground truth, seeded, killed-only, counts, 30 default | done | `eval/mutants.py` + harness; deterministic |
| E3 | Leak prevention (fresh repo, neutral names/paths/env/prompts) | done | `prepare_case` + leak tests |
| E4 | hit@file/module/line±5, fab rates before+after | done | `eval/scoring.py`; captured pre-validation submissions |
| E5 | Three arms incl. heuristic + no-validator ablation | done | harness arms; `skip_validation`/`capture` hooks |
| E6 | Cost guard flags, clean abort | done | `--max-llm-calls/--max-cost`; abort tests |
| E7 | manual_triage.csv + timing script, no invented numbers | done | header-only CSV + `summarize_manual_csv` on tmp data |
| E8 | results.json + RESULTS.md with limitations | done | generator + required-limitations text; stub (no numbers) |
| D1 | service (oneshot + all hardening + 0600 env) | done as config | `deploy/regtriage.service`; never installed/booted |
| D2 | timer daily/persistent, batch template | done as config | `deploy/`; never enabled |
| D3 | INFRA.md single-node Slurm + NFS 2-user + verify commands | done as doc | every command NOT YET RUN |
| R1 | README diagram/quickstart/decisions/security/limits/generated table | done | `README.md`; table honestly empty |
| R2 | RUNBOOK ordered commands | done | `docs/RUNBOOK.md`; all steps NOT YET RUN |
| R3 | INTERVIEW complete | done | 45 Q&A with limitations each |
| R4 | RESULTS stub | done | `docs/RESULTS.md` states no numbers by design |
| P1 | Final self-audit on clean install + dead-code grep | done | clean venv: lockfile+suite+4 tools green; 6 unused-looking names all justified (pydantic validators) |
| P2 | COMPLETION_REPORT even if early | done | this file (run completed fully; nothing cut) |

Notes: `git grep TODO` hits only docs prose ("no TODOs" statements) and
`pass` hits only `passed=` identifiers and `contextlib.suppress` bodies —
no stub bodies. Confirmed by inspection, not just grep.

## Claims in docs NOT verified by a real run

1. No live Anthropic API call has ever been made (wire format unproven).
2. No real simulation has ever run (no Icarus/cocotb here or on CI).
3. No eval numbers exist anywhere (baseline/mutants/arms unexecuted).
4. INFRA.md commands, systemd install/boot, NFS mounts — never run.
5. Slurm tested against shims only, never a real controller.
6. `manual_triage.csv` has zero rows; time-saved math tested on tmp data only.
7. Symlink/make/slurm-shim/POSIX-mode tests skip on Windows (Linux CI runs
   them — confirm in CI logs, not assumed).
8. One transient failure (`test_default_factory...`) seen once in a full
   run, green alone and in two later full runs; cause unidentified.
9. Threshold 0.75 and module/target choices unevaluated (need real eval).
10. `DEFAULT_MODEL_ID` correctness decays with time (dated 2026-10-10).
11. `.secrets.baseline` findings reviewed by automation only; human
    `detect-secrets audit` pending.
12. Clean-install proof is Windows clean venv + Linux CI; no other platform
    verified.
