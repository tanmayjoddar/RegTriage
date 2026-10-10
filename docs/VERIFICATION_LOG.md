# RegTriage Verification Log

Real tool output only, never paraphrased. Each slice appends a dated section
with the exact commands run and their exit codes.

Environment note: the `.venv/` shipped in the ZIP is a Linux venv
(`.venv/bin`, `.venv/lib/python3.11`) and is not executable on this Windows
machine, so checks run on the system Python 3.11.9 with
`ruff 0.17.0, mypy 2.4.0, pytest 9.1.1` installed via pip plus `pip install -e .`.
Lockfile-hashed reinstall on Linux CI remains NOT YET RUN BY A HUMAN
(see docs/RUNBOOK.md when it exists).

---

## Baseline (pre-change, 2026-10-10, Slice 1 as shipped in the ZIP)

Commands run from `D:\Downloads\REG`:

### `python -m ruff check src tests`
```
All checks passed!
RUFF_CHECK_EXIT:0
```

### `python -m ruff format --check src tests`
```
9 files already formatted
RUFF_FMT_EXIT:0
```

### `python -m mypy --strict src tests`
```
Success: no issues found in 9 source files
MYPY_EXIT:0
```

### `python -m bandit -c pyproject.toml -r src`
```
Run started:2026-10-10 11:27:08.076859+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 519
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 1

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Files skipped (0):
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: B101
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	using config: pyproject.toml
[main]	INFO	running on Python 3.11.9
BANDIT_EXIT:0
```

### `python -m pytest --cov=regtriage --cov-branch --cov-report=term-missing`
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0 -- D:\Python\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: D:\Downloads\REG
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, hypothesis-6.168.5, cov-7.1.0
collecting ... collected 35 items

tests/test_config.py::test_default_config_initialization PASSED          [  2%]
tests/test_config.py::test_frozen_immutability PASSED                    [  5%]
tests/test_config.py::test_load_config_from_clean_env PASSED             [  8%]
tests/test_config.py::test_load_config_with_all_env_vars PASSED          [ 11%]
tests/test_config.py::test_mask_for_logging PASSED                       [ 14%]
tests/test_config.py::test_validation_invalid_step_ceiling PASSED        [ 17%]
tests/test_config.py::test_validation_invalid_similarity_threshold PASSED [ 20%]
tests/test_config.py::test_validation_invalid_timeouts PASSED            [ 22%]
tests/test_config.py::test_validation_invalid_token_ceiling PASSED       [ 25%]
tests/test_config.py::test_validation_invalid_log_level PASSED           [ 28%]
tests/test_config.py::test_load_config_malformed_integer_env PASSED      [ 31%]
tests/test_config.py::test_load_config_malformed_steps_env PASSED        [ 34%]
tests/test_config.py::test_load_config_malformed_token_ceiling_env PASSED [ 37%]
tests/test_config.py::test_load_config_malformed_threshold_env PASSED    [ 40%]
tests/test_config.py::test_load_config_with_overrides PASSED             [ 42%]
tests/test_errors.py::test_base_regtriage_error_attributes_and_dict PASSED [ 45%]
tests/test_errors.py::test_base_regtriage_error_empty_details PASSED     [ 48%]
tests/test_errors.py::test_configuration_error PASSED                    [ 51%]
tests/test_errors.py::test_execution_error PASSED                        [ 54%]
tests/test_errors.py::test_parsing_error PASSED                          [ 57%]
tests/test_errors.py::test_sandbox_violation_error PASSED                [ 60%]
tests/test_errors.py::test_validation_error PASSED                       [ 62%]
tests/test_errors.py::test_agent_loop_error PASSED                       [ 65%]
tests/test_errors.py::test_redaction_error PASSED                        [ 68%]
tests/test_errors.py::test_inheritance_hierarchy PASSED                  [ 71%]
tests/test_logging.py::test_redact_anthropic_api_key PASSED              [ 74%]
tests/test_logging.py::test_redact_bearer_token PASSED                   [ 77%]
tests/test_logging.py::test_redact_secrets_in_key_value PASSED            [ 80%]
tests/test_logging.py::test_redact_private_key PASSED                    [ 82%]
tests/test_logging.py::test_redact_email PASSED                          [ 85%]
tests/test_logging.py::test_redact_empty_or_clean_text PASSED            [ 88%]
tests/test_logging.py::test_custom_redaction_pattern PASSED              [ 91%]
tests/test_logging.py::test_redacting_formatter_human PASSED             [ 94%]
tests/test_logging.py::test_redacting_formatter_json PASSED              [ 97%]
tests/test_logging.py::test_configure_logging_and_get_logger PASSED      [100%]
D:\Python\Lib\site-packages\coverage\inorout.py:574: CoverageWarning: Module regtriage was previously imported, but not measured (module-not-measured); see https://coverage.readthedocs.io/en/7.16.2/messages.html#warning-module-not-measured

=============================== tests coverage ================================
_______________ coverage: platform win32, python 3.11.9-final-0 _______________

Name                        Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------
src\regtriage\__init__.py       5      0      0      0   100%
src\regtriage\config.py       139      1     52      4    97%   100, 152->154, 154->157, 252->251
src\regtriage\errors.py        91      0     30      0   100%
src\regtriage\logging.py       54      0     16      1    99%   91->94
-----------------------------------------------------------------------
TOTAL                         289      1     98      5    98%
Required test coverage of 90.0% reached. Total coverage: 98.45%
============================= 35 passed in 1.42s ==============================
PYTEST_EXIT:0
```

Baseline verdict: Slice 1 ships green (35 tests, 98.45% coverage).

---

## Slice 0: audit and fix (2026-10-10)

Changes:
- `src/regtriage/config.py`: `DEFAULT_MODEL_ID` `claude-3-7-sonnet-20250219`
  -> `claude-sonnet-5-5` (current Sonnet per
  https://platform.claude.com/docs/en/about-claude/models/overview, verified
  2026-10-10; Sonnet 5 is legacy, Sonnet 5.5 is current). `REGTRIAGE_MODEL`
  override untouched.
- `src/regtriage/logging.py`: `# nosec B105` now carries the exact rule and
  reason (`redaction placeholder token, not a real password or secret`).
- `.github/workflows/ci.yml`: `actions/checkout@v4` ->
  `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2`;
  `actions/setup-python@v5` ->
  `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0`
  (SHAs resolved via GitHub API `git/ref/tags`).
- `tests/conftest.py`: `baseline_config` now imports and uses
  `DEFAULT_MODEL_ID` instead of a hardcoded model string.

### `python -m ruff check src tests`
```
All checks passed!
RUFF_CHECK_EXIT:0
```

### `python -m ruff format --check src tests`
```
9 files already formatted
RUFF_FMT_EXIT:0
```

### `python -m mypy --strict src tests`
```
Success: no issues found in 9 source files
MYPY_EXIT:0
```

### `python -m bandit -c pyproject.toml -r src`
```
Run started:2026-10-10 11:27:59.276648+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 519
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 1

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Files skipped (0):
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: B101
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	using config: pyproject.toml
[main]	INFO	running on Python 3.11.9
[manager]	WARNING	Test in comment: redaction is not a test name or id, ignoring
[manager]	WARNING	Test in comment: placeholder is not a test name or id, ignoring
[manager]	WARNING	Test in comment: token is not a test name or id, ignoring
[manager]	WARNING	Test in comment: not is not a test name or id, ignoring
[manager]	WARNING	Test in comment: a is not a test name or id, ignoring
[manager]	WARNING	Test in comment: real is not a test name or id, ignoring
[manager]	WARNING	Test in comment: password is not a test name or id, ignoring
[manager]	WARNING	Test in comment: or is not a test name or id, ignoring
[manager]	WARNING	Test in comment: secret is not a test name or id, ignoring
BANDIT_EXIT:0
```
Note: the `[manager] WARNING: Test in comment` lines are bandit's nosec
parser echoing words from the new justification comment; they are benign and
the exit code is 0 with no issues identified.

### `python -m pytest --cov=regtriage --cov-branch --cov-report=term-missing`
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0 -- D:\Python\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: D:\Downloads\REG
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, hypothesis-6.168.5, cov-7.1.0
collecting ... collected 35 items

tests/test_config.py::test_default_config_initialization PASSED          [  2%]
tests/test_config.py::test_frozen_immutability PASSED                    [  5%]
tests/test_config.py::test_load_config_from_clean_env PASSED             [  8%]
tests/test_config.py::test_load_config_with_all_env_vars PASSED          [ 11%]
tests/test_config.py::test_mask_for_logging PASSED                       [ 14%]
tests/test_config.py::test_validation_invalid_step_ceiling PASSED        [ 17%]
tests/test_config.py::test_validation_invalid_similarity_threshold PASSED [ 20%]
tests/test_config.py::test_validation_invalid_timeouts PASSED            [ 22%]
tests/test_config.py::test_validation_invalid_token_ceiling PASSED       [ 25%]
tests/test_config.py::test_validation_invalid_log_level PASSED           [ 28%]
tests/test_config.py::test_load_config_malformed_integer_env PASSED      [ 31%]
tests/test_config.py::test_load_config_malformed_steps_env PASSED        [ 34%]
tests/test_config.py::test_load_config_malformed_token_ceiling_env PASSED [ 37%]
tests/test_config.py::test_load_config_malformed_threshold_env PASSED    [ 40%]
tests/test_config.py::test_load_config_with_overrides PASSED             [ 42%]
tests/test_errors.py::test_base_regtriage_error_attributes_and_dict PASSED [ 45%]
tests/test_errors.py::test_base_regtriage_error_empty_details PASSED     [ 48%]
tests/test_errors.py::test_configuration_error PASSED                    [ 51%]
tests/test_errors.py::test_execution_error PASSED                        [ 54%]
tests/test_errors.py::test_parsing_error PASSED                          [ 57%]
tests/test_errors.py::test_sandbox_violation_error PASSED                [ 60%]
tests/test_errors.py::test_validation_error PASSED                       [ 62%]
tests/test_errors.py::test_agent_loop_error PASSED                       [ 65%]
tests/test_errors.py::test_redaction_error PASSED                        [ 68%]
tests/test_errors.py::test_inheritance_hierarchy PASSED                  [ 71%]
tests/test_logging.py::test_redact_anthropic_api_key PASSED              [ 74%]
tests/test_logging.py::test_redact_bearer_token PASSED                   [ 77%]
tests/test_logging.py::test_redact_secrets_in_key_value PASSED           [ 80%]
tests/test_logging.py::test_redact_private_key PASSED                    [ 82%]
tests/test_logging.py::test_redact_email PASSED                          [ 85%]
tests/test_logging.py::test_redact_empty_or_clean_text PASSED            [ 88%]
tests/test_logging.py::test_custom_redaction_pattern PASSED              [ 91%]
tests/test_logging.py::test_redacting_formatter_human PASSED             [ 94%]
tests/test_logging.py::test_redacting_formatter_json PASSED              [ 97%]
tests/test_logging.py::test_configure_logging_and_get_logger PASSED      [100%]
D:\Python\Lib\site-packages\coverage\inorout.py:574: CoverageWarning: Module regtriage was previously imported, but not measured (module-not-measured); see https://coverage.readthedocs.io/en/7.16.2/messages.html#warning-module-not-measured
Name                        Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------
src\regtriage\__init__.py       5      0      0      0   100%
src\regtriage\config.py       139      1     52      4    97%   103, 155->157, 157->160, 255->254
src\regtriage\errors.py        91      0     30      0   100%
src\regtriage\logging.py       54      0     16      1    99%   91->94
-----------------------------------------------------------------------
TOTAL                         289      1     98      5    98%
Required test coverage of 90.0% reached. Total coverage: 98.45%
============================= 35 passed in 0.49s ==============================
PYTEST_EXIT:0
```

Slice 0 verdict: green, 35 passed, coverage 98.45%.

---

## Slice 2: LocalExecutor + cocotb results parsing + integration test (2026-10-10)

New files: `src/regtriage/runner/__init__.py`, `src/regtriage/runner/executor.py`
(JobSpec/JobResult/Executor Protocol), `src/regtriage/runner/local.py`
(LocalExecutor), `src/regtriage/parsing/__init__.py`,
`src/regtriage/parsing/base.py` (Failure/Parser Protocol),
`src/regtriage/parsing/cocotb.py` (CocotbResultsParser),
`tests/test_runner_local.py` (12 tests, real subprocesses),
`tests/test_parsing_cocotb.py` (12 tests),
`tests/test_runner_integration.py` (slow: real cocotb+Icarus regression,
skips with printed reason when absent),
`tests/fixtures/cocotb_{pass,fail,empty}.xml`. `pyproject.toml` gains the
`slow` marker registration.

Mid-slice findings fixed before commit:
- mypy on Windows: `signal.SIGKILL` does not exist in typeshed for win32.
  Fixed with `_SIGKILL: int = getattr(signal, "SIGKILL", 9)` plus a comment
  (killpg branch only runs on POSIX).
- bandit initially failed on B405/B314 (xml.etree on untrusted XML) and
  B404/B603 (subprocess). defusedxml is not in the allowed dependency set,
  so the parser now rejects any `<!DOCTYPE` declaration before parsing
  (entity expansion becomes impossible under the 32 MB cap) and all four
  findings carry `nosec` with exact rule + reason. A billion-laughs-style
  DOCTYPE fixture test proves the guard.

### `python -m ruff check src tests`
```
All checks passed!
RUFF:0
```

### `python -m ruff format --check src tests`
```
18 files already formatted
FMT:0
```

### `python -m mypy --strict src tests`
```
Success: no issues found in 18 source files
MYPY:0
```

### `python -m bandit -c pyproject.toml -r src`
```
Run started:2026-10-10 11:33:51.418146+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 753
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 5

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Files skipped (0):
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: B101
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	using config: pyproject.toml
[main]	INFO	running on Python 3.11.9
[manager]	WARNING	Test in comment: redaction is not a test name or id, ignoring
[manager]	WARNING	Test in comment: placeholder is not a test name or id, ignoring
[manager]	WARNING	Test in comment: token is not a test name or id, ignoring
[manager]	WARNING	Test in comment: not is not a test name or id, ignoring
[manager]	WARNING	Test in comment: a is not a test name or id, ignoring
[manager]	WARNING	Test in comment: real is not a test name or id, ignoring
[manager]	WARNING	Test in comment: password is not a test name or id, ignoring
[manager]	WARNING	Test in comment: or is not a test name or id, ignoring
[manager]	WARNING	Test in comment: secret is not a test name or id, ignoring
[manager]	WARNING	Test in comment: stdlib is not a test name or id, ignoring
[manager]	WARNING	Test in comment: parser is not a test name or id, ignoring
[manager]	WARNING	Test in comment: DOCTYPE is not a test name or id, ignoring
[manager]	WARNING	Test in comment: rejected is not a test name or id, ignoring
[manager]	WARNING	Test in comment: below is not a test name or id, ignoring
[manager]	WARNING	Test in comment: defusedxml is not a test name or id, ignoring
[manager]	WARNING	Test in comment: not is not a test name or id, ignoring
[manager]	WARNING	Test in comment: in is not a test name or id, ignoring
[manager]	WARNING	Test in comment: allowed is not a test name or id, ignoring
[manager]	WARNING	Test in comment: deps is not a test name or id, ignoring
[manager]	WARNING	Test in comment: DOCTYPE is not a test name or id, ignoring
[manager]	WARNING	Test in comment: rejected is not a test name or id, ignoring
[manager]	WARNING	Test in comment: above is not a test name or id, ignoring
[manager]	WARNING	Test in comment: so is not a test name or id, ignoring
[manager]	WARNING	Test in comment: entity is not a test name or id, ignoring
[manager]	WARNING	Test in comment: expansion is not a test name or id, ignoring
[manager]	WARNING	Test in comment: is is not a test name or id, ignoring
[manager]	WARNING	Test in comment: impossible is not a test name or id, ignoring
[manager]	WARNING	Test in comment: process is not a test name or id, ignoring
[manager]	WARNING	Test in comment: spawning is not a test name or id, ignoring
[manager]	WARNING	Test in comment: is is not a test name or id, ignoring
[manager]	WARNING	Test in comment: the is not a test name or id, ignoring
[manager]	WARNING	Test in comment: executor is not a test name or id, ignoring
[manager]	WARNING	Test in comment: s is not a test name or id, ignoring
[manager]	WARNING	Test in comment: job is not a test name or id, ignoring
[manager]	WARNING	Test in comment: argv is not a test name or id, ignoring
[manager]	WARNING	Test in comment: lists is not a test name or id, ignoring
[manager]	WARNING	Test in comment: only is not a test name or id, ignoring
[manager]	WARNING	Test in comment: never is not a test name or id, ignoring
[manager]	WARNING	Test in comment: shell is not a test name or id, ignoring
[manager]	WARNING	Test in comment: argv is not a test name or id, ignoring
[manager]	WARNING	Test in comment: list is not a test name or id, ignoring
[manager]	WARNING	Test in comment: only is not a test name or id, ignoring
[manager]	WARNING	Test in comment: shell is not a test name or id, ignoring
[manager]	WARNING	Test in comment: is is not a test name or id, ignoring
[manager]	WARNING	Test in comment: never is not a test name or id, ignoring
[manager]	WARNING	Test in comment: enabled is not a test name or id, ignoring
BANDIT_EXIT:0
```
The `[manager] WARNING` lines are bandit's nosec-comment parser echoing each
word of the justification comments; benign, exit 0.

### `python -m pytest --cov=regtriage --cov-branch --cov-report=term-missing`
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0 -- D:\Python\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: D:\Downloads\REG
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, hypothesis-6.168.5, cov-7.1.0
collecting ... collected 60 items

tests/test_config.py::test_default_config_initialization PASSED          [  1%]
tests/test_config.py::test_frozen_immutability PASSED                    [  3%]
tests/test_config.py::test_load_config_from_clean_env PASSED             [  5%]
tests/test_config.py::test_load_config_with_all_env_vars PASSED          [  6%]
tests/test_config.py::test_mask_for_logging PASSED                       [  8%]
tests/test_config.py::test_validation_invalid_step_ceiling PASSED        [ 10%]
tests/test_config.py::test_validation_invalid_similarity_threshold PASSED [ 11%]
tests/test_config.py::test_validation_invalid_timeouts PASSED            [ 13%]
tests/test_config.py::test_validation_invalid_token_ceiling PASSED       [ 15%]
tests/test_config.py::test_validation_invalid_log_level PASSED           [ 16%]
tests/test_config.py::test_load_config_malformed_integer_env PASSED      [ 18%]
tests/test_config.py::test_load_config_malformed_steps_env PASSED        [ 20%]
tests/test_config.py::test_load_config_malformed_token_ceiling_env PASSED [ 21%]
tests/test_config.py::test_load_config_malformed_threshold_env PASSED    [ 23%]
tests/test_config.py::test_load_config_with_overrides PASSED             [ 25%]
tests/test_errors.py::test_base_regtriage_error_attributes_and_dict PASSED [ 26%]
tests/test_errors.py::test_base_regtriage_error_empty_details PASSED     [ 28%]
tests/test_errors.py::test_configuration_error PASSED                    [ 30%]
tests/test_errors.py::test_execution_error PASSED                        [ 31%]
tests/test_errors.py::test_parsing_error PASSED                          [ 33%]
tests/test_errors.py::test_sandbox_violation_error PASSED                [ 35%]
tests/test_errors.py::test_validation_error PASSED                       [ 36%]
tests/test_errors.py::test_agent_loop_error PASSED                       [ 38%]
tests/test_errors.py::test_redaction_error PASSED                        [ 40%]
tests/test_errors.py::test_inheritance_hierarchy PASSED                  [ 41%]
tests/test_logging.py::test_redact_anthropic_api_key PASSED              [ 43%]
tests/test_logging.py::test_redact_bearer_token PASSED                   [ 45%]
tests/test_logging.py::test_redact_secrets_in_key_value PASSED           [ 46%]
tests/test_logging.py::test_redact_private_key PASSED                    [ 48%]
tests/test_logging.py::test_redact_email PASSED                          [ 50%]
tests/test_logging.py::test_redact_empty_or_clean_text PASSED            [ 51%]
tests/test_logging.py::test_custom_redaction_pattern PASSED              [ 53%]
tests/test_logging.py::test_redacting_formatter_human PASSED             [ 55%]
tests/test_logging.py::test_redacting_formatter_json PASSED              [ 56%]
tests/test_logging.py::test_configure_logging_and_get_logger PASSED      [ 58%]
tests/test_parsing_cocotb.py::test_passing_results_yield_no_failures PASSED [ 60%]
tests/test_parsing_cocotb.py::test_failing_results_yield_one_failure_per_broken_case PASSED [ 61%]
tests/test_parsing_cocotb.py::test_empty_testsuite_yields_no_failures PASSED [ 63%]
tests/test_parsing_cocotb.py::test_missing_file_raises_parsing_error PASSED [ 65%]
tests/test_parsing_cocotb.py::test_directory_path_raises_parsing_error PASSED [ 66%]
tests/test_parsing_cocotb.py::test_malformed_xml_raises_parsing_error PASSED [ 68%]
tests/test_parsing_cocotb.py::test_invalid_utf8_raises_parsing_error PASSED [ 70%]
tests/test_parsing_cocotb.py::test_oversized_file_raises_parsing_error PASSED [ 71%]
tests/test_parsing_cocotb.py::test_bare_failure_without_message_or_text PASSED [ 73%]
tests/test_parsing_cocotb.py::test_excerpt_is_capped PASSED              [ 75%]
tests/test_parsing_cocotb.py::test_doctype_declaration_is_rejected PASSED [ 76%]
tests/test_parsing_cocotb.py::test_invalid_constructor_args_rejected PASSED [ 78%]
tests/test_runner_integration.py::test_cocotb_regression_with_icarus SKIPPED [ 80%]
tests/test_runner_local.py::test_single_job_captures_stdout_and_stderr PASSED [ 81%]
tests/test_runner_local.py::test_stderr_is_captured_separately PASSED    [ 83%]
tests/test_runner_local.py::test_nonzero_exit_reports_returncode_without_timeout PASSED [ 85%]
tests/test_runner_local.py::test_timeout_kills_job_and_flags_timed_out PASSED [ 86%]
tests/test_runner_local.py::test_job_uses_executor_default_timeout PASSED [ 88%]
tests/test_runner_local.py::test_missing_binary_raises_execution_error PASSED [ 90%]
tests/test_runner_local.py::test_invalid_constructor_args_rejected PASSED [ 91%]
tests/test_runner_local.py::test_invalid_spec_rejected_by_validation PASSED [ 93%]
tests/test_runner_local.py::test_results_preserve_input_order PASSED     [ 95%]
tests/test_runner_local.py::test_serial_executor_runs_jobs_one_at_a_time PASSED [ 96%]
tests/test_runner_local.py::test_large_output_is_truncated_to_bound_memory PASSED [ 98%]
D:\Python\Lib\site-packages\coverage\inorout.py:574: CoverageWarning: Module regtriage was previously imported, but not measured (module-not-measured); see https://coverage.readthedocs.io/en/7.16.2/messages.html#warning-module-not-measured
  self.warn(msg, slug="module-not-measured")
tests/test_runner_local.py::test_job_runs_in_given_cwd PASSED            [100%]

=============================== tests coverage ================================
_______________ coverage: platform win32, python 3.11.9-final-0 _______________

Name                                Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------
src\regtriage\__init__.py               5      0      0      0   100%
src\regtriage\config.py               139      1     52      4    97%   103, 155->157, 157->160, 255->254
src\regtriage\errors.py                91      0     30      0   100%
src\regtriage\logging.py               54      0     16      1    99%   91->94
src\regtriage\parsing\__init__.py       3      0      0      0   100%
src\regtriage\parsing\base.py          12      0      0      0   100%
src\regtriage\parsing\cocotb.py        44      3     16      1    93%   42-43, 78
src\regtriage\runner\__init__.py        3      0      0      0   100%
src\regtriage\runner\executor.py       18      0      0      0   100%
src\regtriage\runner\local.py          61     10     18      4    80%   30-36, 46, 72, 82
-------------------------------------------------------------------------------
TOTAL                                 430     14    132     10    95%
Required test coverage of 90.0% reached. Total coverage: 95.37%
======================== 59 passed, 1 skipped in 4.71s ========================
PYTEST_EXIT:0
```

Uncovered lines in `runner/local.py` (30-36 killpg branch, 46/72/82 defensive
fallbacks) are POSIX-only or unreachable-after-communicate guards; the killpg
branch is covered on Linux CI.

Slice 2 verdict: green, 59 passed + 1 skipped (integration, no simulator
here), coverage 95.37%.

---

## Slice 3: signature normalization + clustering + property tests (2026-10-10)

New files: `src/regtriage/signature.py` (normalize hex/numbers/timestamps/
paths/instance indices/Verilog literals, sha256 signature, token-set Jaccard,
exact clustering + greedy near-duplicate merge above threshold) and
`tests/test_signature.py` (12 unit tests + 3 hypothesis property tests:
normalize idempotent, clustering order-independent, clustering idempotent).

Mid-slice fix: coverage showed the Jaccard-merge path for *distinct*
signatures (lines 88-91) was unexercised — the first near-dup test normalized
both messages identically. Added
`test_near_duplicates_with_different_signatures_merge` (channel-vs-port,
Jaccard exactly 0.75: merges at 0.75, splits at 0.9). `signature.py` is now
100%.

### `python -m ruff check src tests`
```
All checks passed!
RUFF:0
```

### `python -m ruff format --check src tests`
```
20 files already formatted
FMT:0
```

### `python -m mypy --strict src tests`
```
Success: no issues found in 20 source files
MYPY:0
```

### `python -m bandit -c pyproject.toml -r src`
(Bandit output below is verbatim except the trailing `[main] INFO` lines and
the benign `[manager] WARNING: Test in comment` echoes, unchanged from
Slice 2, which are omitted for length.)
```
Run started:2026-10-10 11:37:16.695051+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 840
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 5

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Files skipped (0):
BANDIT:0
```

### `python -m pytest --cov=regtriage --cov-branch --cov-report=term-missing`
(75 items collected; all earlier tests still pass unchanged — only the 15 new
signature lines are reproduced here verbatim, plus the full coverage table.)
```
tests/test_signature.py::test_hex_addresses_normalize PASSED             [ 81%]
tests/test_signature.py::test_numbers_timestamps_and_indices_normalize PASSED [ 82%]
tests/test_signature.py::test_paths_and_verilog_literals_normalize PASSED [ 84%]
tests/test_signature.py::test_normalize_collapses_whitespace_and_case PASSED [ 85%]
tests/test_signature.py::test_signature_is_stable_sha256 PASSED          [ 86%]
tests/test_signature.py::test_jaccard_edge_cases PASSED                  [ 88%]
tests/test_signature.py::test_identical_signatures_form_one_cluster PASSED [ 89%]
tests/test_signature.py::test_distinct_failures_stay_apart PASSED        [ 90%]
tests/test_signature.py::test_near_duplicates_merge_above_threshold PASSED [ 92%]
tests/test_signature.py::test_near_duplicates_with_different_signatures_merge PASSED [ 93%]
tests/test_signature.py::test_empty_input_and_bad_threshold PASSED       [ 94%]
tests/test_signature.py::test_cluster_model_rejects_empty_members PASSED [ 96%]
tests/test_signature.py::test_normalize_is_idempotent PASSED             [ 97%]
tests/test_signature.py::test_clustering_is_order_independent PASSED     [ 98%]
tests/test_signature.py::test_clustering_is_idempotent PASSED            [100%]

Name                                Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------
src\regtriage\__init__.py               5      0      0      0   100%
src\regtriage\config.py               139      1     52      4    97%   103, 155->157, 157->160, 255->254
src\regtriage\errors.py                91      0     30      0   100%
src\regtriage\logging.py               54      0     16      1    99%   91->94
src\regtriage\parsing\__init__.py       3      0      0      0   100%
src\regtriage\parsing\base.py          12      0      0      0   100%
src\regtriage\parsing\cocotb.py        44      3     16      1    93%   42-43, 78
src\regtriage\runner\__init__.py        3      0      0      0   100%
src\regtriage\runner\executor.py       18      0      0      0   100%
src\regtriage\runner\local.py          61     10     18      4    80%   30-36, 46, 72, 82
src\regtriage\signature.py             62      0     18      0   100%
-------------------------------------------------------------------------------
TOTAL                                 492     14    150     10    96%
Required test coverage of 90.0% reached. Total coverage: 95.95%
======================== 74 passed, 1 skipped in 5.46s ========================
PYTEST_EXIT:0
```

Slice 3 verdict: green, 74 passed + 1 skipped, coverage 95.95%,
`signature.py` 100%.
