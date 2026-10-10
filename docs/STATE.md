# RegTriage Run State (updated after every slice)

- Last completed slice: 6 (agent loop, clients, redaction, audit, injection
  tests)
- What is done:
  - Slices 0, 2, 3, 4, 5 committed (e51b79e, 1de80f0, a5d2701, 22e06e8,
    e950a79); CI fix 28a75f3; CI matrix job 57115b3 (run #5 success on
    ubuntu AND windows); docs note 94ddefd (run #4 success).
  - Slice 6: `src/regtriage/agent/` (protocol, AnthropicClient,
    ReplayClient, Diagnosis + failed_evidence, tool schemas + ToolRuntime,
    triage_cluster) and `src/regtriage/audit.py` (JSONL 0600). Tests:
    31 agent + 4 audit, all via ReplayClient / recording fakes, no network.
  - 158 passed + 3 skipped, coverage 97.21%; agent/* + audit.py at 100%.
    All 5 checks green (bandit: 7 justified nosecs); log + INTERVIEW updated.
- Exact next step: Slice 7 — reports + Slack + escaping. New:
  `src/regtriage/report/` (JSON + Markdown generators escaping all
  untrusted text; optional Slack webhook with URL from env only, escaped,
  timeout). Tests incl. escaping adversarial cases; +5 INTERVIEW Q&A;
  log entry; commit "slice 7: ...". (Slack webhook = cut candidate #2 if
  budget forces it — build reports first, Slack second.)
- Open issues:
  - Live Anthropic calls NEVER made; real wire format unverified by tests.
  - Forced submissions carry no quality marker (see INTERVIEW slice 6 Q3).
  - `.pre-commit-config.yaml` with detect-secrets hook still to write
    (Slice 11 with docs).
  - `.venv/` Linux-only; Windows box uses system Python 3.11.9.
  - cocotb+Icarus integration never executed; real sim on Linux NOT YET
    RUN BY A HUMAN. Skips: "iverilog not installed",
    "cannot create symlinks on this machine" (runs on Linux CI),
    "POSIX file modes do not apply on this platform".
  - RUNBOOK.md lands in Slice 11; until then human-only items live here.
  - Threshold default 0.75 unevaluated on real logs; revisit with Slice 8.
  - Template leftovers kept untouched and untracked. Planned removal in
    Slice 11 (explicit, not silent).
