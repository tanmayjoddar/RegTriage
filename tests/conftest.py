"""Shared pytest fixtures for RegTriage test suite."""

from collections.abc import Generator
from pathlib import Path

import pytest

from regtriage.config import DEFAULT_MODEL_ID, RegTriageConfig


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Provide an isolated temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Generator[pytest.MonkeyPatch, None, None]:
    """Ensure environment is isolated from ambient credentials during testing."""
    for key in [
        "ANTHROPIC_API_KEY",
        "REGTRIAGE_MODEL",
        "REGTRIAGE_WORKSPACE_ROOT",
        "REGTRIAGE_REPO_PATH",
        "REGTRIAGE_RESULTS_XML",
        "REGTRIAGE_TIMEOUT",
        "REGTRIAGE_MAX_STEPS",
        "REGTRIAGE_TOKEN_CEILING",
        "REGTRIAGE_SIMILARITY_THRESHOLD",
        "SLACK_WEBHOOK_URL",
        "REGTRIAGE_AUDIT_LOG",
        "REGTRIAGE_OFFLINE",
        "REGTRIAGE_LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield monkeypatch


@pytest.fixture
def baseline_config(temp_workspace: Path) -> RegTriageConfig:
    """Return a validated base configuration pointing to an isolated directory."""
    return RegTriageConfig(
        workspace_root=temp_workspace,
        model_id=DEFAULT_MODEL_ID,
        max_agent_steps=8,
        token_ceiling=50_000,
        similarity_threshold=0.8,
        timeout_seconds=60,
    )
