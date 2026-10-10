# RegTriage runbook: every human step, in order

Each command is exact. Anything marked NOT YET RUN BY A HUMAN has not been
executed by a human on the target platform at the time of writing.

## 1. Python environment

```bash
python3.11 --version  # need >= 3.11 — NOT YET RUN BY A HUMAN
python3.11 -m venv .venv && . .venv/bin/activate  # NOT YET RUN BY A HUMAN
pip install --require-hashes --no-deps -r requirements.lock  # NOT YET RUN BY A HUMAN
pip install -e .  # NOT YET RUN BY A HUMAN
```

## 2. EDA toolchain (Linux)

```bash
sudo apt-get install -y iverilog  # NOT YET RUN BY A HUMAN
iverilog -V  # NOT YET RUN BY A HUMAN
pip install cocotb cocotb-test cocotbext-axi cocotbext-pcie  # versions per tb/README — NOT YET RUN BY A HUMAN
```

## 3. Pin the upstream checkout (MIT, not taxi)

```bash
git clone https://github.com/alexforencich/verilog-pcie.git  # NOT YET RUN BY A HUMAN
cd verilog-pcie && git checkout 25156a9a162c41c60f11f41590c7d006d015ae5a  # NOT YET RUN BY A HUMAN
head -5 LICENSE  # expect MIT text; must NOT be CERN-OHL-S/taxi — NOT YET RUN BY A HUMAN
```

## 4. Baseline must be green before any eval

```bash
cd tb/dma_psdpram && make  # NOT YET RUN BY A HUMAN
cd ../irq_rate_limit && make  # NOT YET RUN BY A HUMAN
cd ../dma_if_axi && make  # NOT YET RUN BY A HUMAN
```

All three must pass. If any fails, stop — do not run eval.

## 5. API key and first triage run

```bash
export ANTHROPIC_API_KEY="sk-ant-..."  # env only, never argv — NOT YET RUN BY A HUMAN
regtriage validate-config  # NOT YET RUN BY A HUMAN
regtriage run --repo /path/verilog-pcie --results-xml /path/results.xml --out out/  # NOT YET RUN BY A HUMAN
regtriage run --repo /path/verilog-pcie --results-xml /path/results.xml --out out/ --offline  # no network — NOT YET RUN BY A HUMAN
```

## 6. Full eval (default 30 mutants; needs key + toolchain + time)

```bash
regtriage eval --repo /path/verilog-pcie --work eval-work --mutants 30 --seed 0 --max-llm-calls 200 --max-cost 20.0 --out eval/results.json  # NOT YET RUN BY A HUMAN
regtriage eval-report --results eval/results.json --out-md docs/RESULTS.md --manual-csv eval/manual_triage.csv  # NOT YET RUN BY A HUMAN
```

## 7. Manual timing (stopwatch, your numbers only)

```bash
# Triage each killed mutant by hand; time yourself with a stopwatch.
# Append one row per case to eval/manual_triage.csv:
# case_id,file,operator,manual_seconds,notes
regtriage eval-report --results eval/results.json --out-md docs/RESULTS.md --manual-csv eval/manual_triage.csv  # recompute — NOT YET RUN BY A HUMAN
```

Never invent these numbers; the CSV ships header-only for that reason.

## 8. Slurm + NFS + systemd (see docs/INFRA.md for the full sequence)

```bash
sinfo && scontrol ping  # NOT YET RUN BY A HUMAN
sudo cp deploy/regtriage.service deploy/regtriage.timer /etc/systemd/system/  # NOT YET RUN BY A HUMAN
sudo systemctl daemon-reload && sudo systemctl enable --now regtriage.timer  # NOT YET RUN BY A HUMAN
```

## 9. Secrets hygiene

```bash
detect-secrets audit .secrets.baseline  # mark the 8 known-fake fixtures — NOT YET RUN BY A HUMAN
pre-commit install  # NOT YET RUN BY A HUMAN
```

## 10. Live Gemini 2-turn tool-call integration test

```bash
export GEMINI_API_KEY="AIzaSy..."  # env only, never commit — NOT YET RUN BY A HUMAN
pytest tests/test_gemini.py -k test_live_gemini_two_turn_tool_call -q --no-cov  # NOT YET RUN BY A HUMAN
```

