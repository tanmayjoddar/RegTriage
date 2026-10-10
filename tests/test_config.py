"""Tests for configuration validation, environment parsing, and secret isolation."""

from pathlib import Path

import pytest
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from regtriage.config import DEFAULT_MODEL_ID, RegTriageConfig, load_config
from regtriage.errors import ConfigurationError


def test_default_config_initialization(temp_workspace: Path) -> None:
    config = RegTriageConfig(workspace_root=temp_workspace)
    assert config.workspace_root == temp_workspace.resolve()
    assert config.model_id == DEFAULT_MODEL_ID
    assert config.max_agent_steps == 8
    assert config.token_ceiling == 100_000
    assert config.similarity_threshold == 0.75
    assert config.timeout_seconds == 120
    assert config.subprocesses_timeout_seconds == 30
    assert config.offline_mode is False
    assert config.log_level == "INFO"
    assert config.anthropic_api_key is None
    assert config.slack_webhook_url is None


def test_frozen_immutability(baseline_config: RegTriageConfig) -> None:
    with pytest.raises(PydanticValidationError):
        baseline_config.max_agent_steps = 10


def test_load_config_from_clean_env(clean_env: pytest.MonkeyPatch, temp_workspace: Path) -> None:
    config = load_config(env={}, overrides={"workspace_root": temp_workspace})
    assert config.workspace_root == temp_workspace.resolve()
    assert config.anthropic_api_key is None
    assert config.model_id == DEFAULT_MODEL_ID


def test_load_config_with_all_env_vars(
    clean_env: pytest.MonkeyPatch,
    temp_workspace: Path,
) -> None:
    audit_file = temp_workspace / "audit.jsonl"
    results_xml = temp_workspace / "results.xml"
    repo_dir = temp_workspace / "verilog-pcie"
    env_vars = {
        "ANTHROPIC_API_KEY": "sk-ant-testkey12345678901234567890",
        "REGTRIAGE_MODEL": "claude-3-5-sonnet-20241022",
        "REGTRIAGE_WORKSPACE_ROOT": str(temp_workspace),
        "REGTRIAGE_REPO_PATH": str(repo_dir),
        "REGTRIAGE_RESULTS_XML": str(results_xml),
        "REGTRIAGE_TIMEOUT": "180",
        "REGTRIAGE_MAX_STEPS": "12",
        "REGTRIAGE_TOKEN_CEILING": "80000",
        "REGTRIAGE_SIMILARITY_THRESHOLD": "0.85",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T00/B00/X00",
        "REGTRIAGE_AUDIT_LOG": str(audit_file),
        "REGTRIAGE_OFFLINE": "true",
        "REGTRIAGE_LOG_LEVEL": "debug",
    }
    config = load_config(env=env_vars)
    assert config.anthropic_api_key is not None
    assert config.anthropic_api_key.get_secret_value() == "sk-ant-testkey12345678901234567890"
    assert config.model_id == "claude-3-5-sonnet-20241022"
    assert config.workspace_root == temp_workspace.resolve()
    assert config.repo_path == repo_dir.resolve()
    assert config.results_xml_path == results_xml.resolve()
    assert config.timeout_seconds == 180
    assert config.max_agent_steps == 12
    assert config.token_ceiling == 80000
    assert config.similarity_threshold == 0.85
    assert config.slack_webhook_url is not None
    assert (
        config.slack_webhook_url.get_secret_value()
        == "https://hooks.slack.com/services/T00/B00/X00"
    )
    assert config.audit_log_path == audit_file.resolve()
    assert config.offline_mode is True
    assert config.log_level == "DEBUG"


def test_mask_for_logging(temp_workspace: Path) -> None:
    config = RegTriageConfig(
        workspace_root=temp_workspace,
        anthropic_api_key=SecretStr("sk-ant-verysecretkey123456789"),
        slack_webhook_url=SecretStr("https://hooks.slack.com/test"),
    )
    masked = config.mask_for_logging()
    assert masked["anthropic_api_key"] == "[MASKED_KEY]"
    assert masked["slack_webhook_url"] == "[MASKED_WEBHOOK]"
    assert "sk-ant-verysecretkey123456789" not in str(masked)
    assert isinstance(masked["workspace_root"], str)


def test_validation_invalid_step_ceiling(temp_workspace: Path) -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(overrides={"workspace_root": temp_workspace, "max_agent_steps": 0})
    assert "max_agent_steps" in str(exc_info.value)

    with pytest.raises(ConfigurationError) as exc_info2:
        load_config(overrides={"workspace_root": temp_workspace, "max_agent_steps": 100})
    assert "max_agent_steps" in str(exc_info2.value)


def test_validation_invalid_similarity_threshold(temp_workspace: Path) -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(overrides={"workspace_root": temp_workspace, "similarity_threshold": 1.5})
    assert "similarity_threshold" in str(exc_info.value)

    with pytest.raises(ConfigurationError) as exc_info2:
        load_config(overrides={"workspace_root": temp_workspace, "similarity_threshold": -0.1})
    assert "similarity_threshold" in str(exc_info2.value)


def test_validation_invalid_timeouts(temp_workspace: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_config(overrides={"workspace_root": temp_workspace, "timeout_seconds": 0})

    with pytest.raises(ConfigurationError):
        load_config(
            overrides={"workspace_root": temp_workspace, "subprocesses_timeout_seconds": -5}
        )


def test_validation_invalid_token_ceiling(temp_workspace: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_config(overrides={"workspace_root": temp_workspace, "token_ceiling": -100})


def test_validation_invalid_log_level(temp_workspace: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_config(overrides={"workspace_root": temp_workspace, "log_level": "VERBOSE"})


def test_load_config_malformed_integer_env() -> None:
    bad_env = {"REGTRIAGE_TIMEOUT": "not_a_number"}
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(env=bad_env)
    assert exc_info.value.parameter_name == "REGTRIAGE_TIMEOUT"


def test_load_config_malformed_steps_env() -> None:
    bad_env = {"REGTRIAGE_MAX_STEPS": "abc"}
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(env=bad_env)
    assert exc_info.value.parameter_name == "REGTRIAGE_MAX_STEPS"


def test_load_config_malformed_token_ceiling_env() -> None:
    bad_env = {"REGTRIAGE_TOKEN_CEILING": "xyz"}
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(env=bad_env)
    assert exc_info.value.parameter_name == "REGTRIAGE_TOKEN_CEILING"


def test_load_config_malformed_threshold_env() -> None:
    bad_env = {"REGTRIAGE_SIMILARITY_THRESHOLD": "not_a_float"}
    with pytest.raises(ConfigurationError) as exc_info:
        load_config(env=bad_env)
    assert exc_info.value.parameter_name == "REGTRIAGE_SIMILARITY_THRESHOLD"


def test_load_config_with_overrides(temp_workspace: Path) -> None:
    config = load_config(
        env={},
        overrides={"timeout_seconds": 300, "workspace_root": temp_workspace},
    )
    assert config.timeout_seconds == 300
    assert config.workspace_root == temp_workspace.resolve()
