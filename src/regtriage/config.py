"""Validated configuration models and environment loader for RegTriage."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from regtriage.errors import ConfigurationError

# Default current Anthropic Sonnet model ID if not explicitly configured.
# Verified against https://platform.claude.com/docs/en/about-claude/models/overview
# on 2026-10-10: the current Sonnet model is Claude Sonnet 5.5 with Claude API
# model ID "claude-sonnet-5-5" (Sonnet 5 is legacy). Override with REGTRIAGE_MODEL.
DEFAULT_MODEL_ID = "claude-sonnet-5-5"

# Default Gemini model ID if not explicitly configured. Verified against
# https://ai.google.dev/gemini-api/docs/models on 2026-10-10: the GA default
# for new agent work is Gemini 3.8 Flash. Config-only: override with
# REGTRIAGE_GEMINI_MODEL; never hardcode elsewhere.
DEFAULT_GEMINI_MODEL_ID = "gemini-3.8-flash"


class RegTriageConfig(BaseModel):
    """Runtime configuration for regression runner, clustering, and agent triage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_root: Path = Field(
        default_factory=Path.cwd,
        description="Root directory for file confinement and repository paths",
    )
    repo_path: Path | None = Field(
        default=None,
        description="Path to target hardware repository checkout",
    )
    results_xml_path: Path | None = Field(
        default=None,
        description="Path to cocotb results.xml file or parent simulation directory",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key, populated strictly from ANTHROPIC_API_KEY env",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        description="Gemini API key, populated strictly from GEMINI_API_KEY/GOOGLE_API_KEY env",
    )
    provider: Literal["anthropic", "gemini"] = Field(
        default="anthropic",
        description="LLM provider selected via REGTRIAGE_PROVIDER environment variable",
    )
    model_id: str = Field(
        default=DEFAULT_MODEL_ID,
        description="Model ID configured via REGTRIAGE_MODEL environment variable or CLI",
    )
    gemini_model_id: str = Field(
        default=DEFAULT_GEMINI_MODEL_ID,
        description="Gemini model ID configured via REGTRIAGE_GEMINI_MODEL environment variable",
    )
    max_agent_steps: int = Field(
        default=8,
        description="Maximum tool calls permitted per cluster investigation",
    )
    token_ceiling: int = Field(
        default=100_000,
        description="Total token ceiling per cluster triage session",
    )
    similarity_threshold: float = Field(
        default=0.75,
        description="Jaccard similarity threshold for merging near-duplicate clusters",
    )
    timeout_seconds: int = Field(
        default=120,
        description="Global timeout in seconds for individual test execution and agent sessions",
    )
    subprocesses_timeout_seconds: int = Field(
        default=30,
        description="Timeout in seconds for internal tool invocations (git, grep)",
    )
    slack_webhook_url: SecretStr | None = Field(
        default=None,
        description="Slack incoming webhook URL, loaded strictly from SLACK_WEBHOOK_URL",
    )
    audit_log_path: Path | None = Field(
        default=None,
        description="Path to append-only JSONL audit log file (permissions 0600)",
    )
    offline_mode: bool = Field(
        default=False,
        description="When True, prevents network egress and records mock/audit actions",
    )
    log_level: str = Field(
        default="INFO",
        description="Standard logging verbosity level",
    )
    max_tool_output_bytes: int = Field(
        default=65_536,
        description="Maximum byte count returned by any individual read-only tool invocation",
    )
    max_tool_lines: int = Field(
        default=200,
        description="Maximum number of lines returned by read-only tools",
    )

    @field_validator("workspace_root", "repo_path", "results_xml_path", "audit_log_path")
    @classmethod
    def resolve_paths(cls, value: Path | None) -> Path | None:
        """Resolve path to absolute form when provided."""
        if value is None:
            return None
        return value.expanduser().resolve()

    @field_validator("max_agent_steps")
    @classmethod
    def validate_steps(cls, value: int) -> int:
        """Ensure max agent steps is within operational boundaries."""
        if value <= 0 or value > 50:
            raise ValueError(f"max_agent_steps must be between 1 and 50, got {value}")
        return value

    @field_validator("token_ceiling")
    @classmethod
    def validate_token_ceiling(cls, value: int) -> int:
        """Ensure token ceiling is positive."""
        if value <= 0:
            raise ValueError(f"token_ceiling must be positive, got {value}")
        return value

    @field_validator("similarity_threshold")
    @classmethod
    def validate_similarity_threshold(cls, value: float) -> float:
        """Ensure similarity threshold is between 0.0 and 1.0."""
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"similarity_threshold must be between 0.0 and 1.0, got {value}",
            )
        return value

    @field_validator("timeout_seconds", "subprocesses_timeout_seconds")
    @classmethod
    def validate_timeouts(cls, value: int) -> int:
        """Ensure execution timeouts are positive integers."""
        if value <= 0:
            raise ValueError(f"Timeout values must be positive, got {value}")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Ensure log level matches standard logging names."""
        normalized = value.upper().strip()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in valid_levels:
            raise ValueError(
                f"log_level must be one of {sorted(valid_levels)}, got {value}",
            )
        return normalized

    def mask_for_logging(self) -> dict[str, Any]:
        """Produce a safe dictionary representation with all secret values masked."""
        data = self.model_dump()
        if self.anthropic_api_key is not None:
            data["anthropic_api_key"] = "[MASKED_KEY]"
        if self.gemini_api_key is not None:
            data["gemini_api_key"] = "[MASKED_KEY]"
        if self.slack_webhook_url is not None:
            data["slack_webhook_url"] = "[MASKED_WEBHOOK]"
        # Convert Path objects to string for serializability
        for k, v in data.items():
            if isinstance(v, Path):
                data[k] = str(v)
        return data


def load_config(
    env: Mapping[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> RegTriageConfig:
    """Load configuration from environment variables and explicit CLI overrides."""
    source_env = os.environ if env is None else env
    raw_data: dict[str, Any] = {}

    # Extract secrets strictly from environment
    api_key_str = source_env.get("ANTHROPIC_API_KEY")
    if api_key_str and api_key_str.strip():
        raw_data["anthropic_api_key"] = SecretStr(api_key_str.strip())

    gemini_key_str = source_env.get("GEMINI_API_KEY") or source_env.get("GOOGLE_API_KEY")
    if gemini_key_str and gemini_key_str.strip():
        raw_data["gemini_api_key"] = SecretStr(gemini_key_str.strip())

    slack_url = source_env.get("SLACK_WEBHOOK_URL")
    if slack_url and slack_url.strip():
        raw_data["slack_webhook_url"] = SecretStr(slack_url.strip())

    # Environment variables
    provider_env = source_env.get("REGTRIAGE_PROVIDER")
    if provider_env and provider_env.strip():
        raw_data["provider"] = provider_env.strip().lower()

    model_env = source_env.get("REGTRIAGE_MODEL")
    if model_env and model_env.strip():
        raw_data["model_id"] = model_env.strip()

    gemini_model_env = source_env.get("REGTRIAGE_GEMINI_MODEL")
    if gemini_model_env and gemini_model_env.strip():
        raw_data["gemini_model_id"] = gemini_model_env.strip()

    workspace_env = source_env.get("REGTRIAGE_WORKSPACE_ROOT")
    if workspace_env and workspace_env.strip():
        raw_data["workspace_root"] = Path(workspace_env.strip())

    repo_env = source_env.get("REGTRIAGE_REPO_PATH")
    if repo_env and repo_env.strip():
        raw_data["repo_path"] = Path(repo_env.strip())

    results_env = source_env.get("REGTRIAGE_RESULTS_XML")
    if results_env and results_env.strip():
        raw_data["results_xml_path"] = Path(results_env.strip())

    timeout_env = source_env.get("REGTRIAGE_TIMEOUT")
    if timeout_env and timeout_env.strip():
        try:
            raw_data["timeout_seconds"] = int(timeout_env.strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid integer for REGTRIAGE_TIMEOUT: {timeout_env}",
                parameter_name="REGTRIAGE_TIMEOUT",
            ) from exc

    steps_env = source_env.get("REGTRIAGE_MAX_STEPS")
    if steps_env and steps_env.strip():
        try:
            raw_data["max_agent_steps"] = int(steps_env.strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid integer for REGTRIAGE_MAX_STEPS: {steps_env}",
                parameter_name="REGTRIAGE_MAX_STEPS",
            ) from exc

    token_ceiling_env = source_env.get("REGTRIAGE_TOKEN_CEILING")
    if token_ceiling_env and token_ceiling_env.strip():
        try:
            raw_data["token_ceiling"] = int(token_ceiling_env.strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid integer for REGTRIAGE_TOKEN_CEILING: {token_ceiling_env}",
                parameter_name="REGTRIAGE_TOKEN_CEILING",
            ) from exc

    threshold_env = source_env.get("REGTRIAGE_SIMILARITY_THRESHOLD")
    if threshold_env and threshold_env.strip():
        try:
            raw_data["similarity_threshold"] = float(threshold_env.strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid float for REGTRIAGE_SIMILARITY_THRESHOLD: {threshold_env}",
                parameter_name="REGTRIAGE_SIMILARITY_THRESHOLD",
            ) from exc

    audit_env = source_env.get("REGTRIAGE_AUDIT_LOG")
    if audit_env and audit_env.strip():
        raw_data["audit_log_path"] = Path(audit_env.strip())

    offline_env = source_env.get("REGTRIAGE_OFFLINE")
    if offline_env is not None:
        raw_data["offline_mode"] = offline_env.strip().lower() in {"1", "true", "yes"}

    log_level_env = source_env.get("REGTRIAGE_LOG_LEVEL")
    if log_level_env and log_level_env.strip():
        raw_data["log_level"] = log_level_env.strip()

    # Apply explicit overrides if provided
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                raw_data[k] = v

    try:
        return RegTriageConfig(**raw_data)
    except PydanticValidationError as exc:
        first_error = exc.errors()[0]
        field_name = str(first_error.get("loc", ["unknown"])[0])
        msg = first_error.get("msg", "Validation error")
        raise ConfigurationError(
            f"Configuration error for '{field_name}': {msg}",
            parameter_name=field_name,
            details={"pydantic_errors": exc.errors()},
        ) from exc
