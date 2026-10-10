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
