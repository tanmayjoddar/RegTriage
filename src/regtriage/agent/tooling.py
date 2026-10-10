"""Tool schemas exposed to the model and the dispatcher that runs them."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from regtriage.agent.diagnosis import Diagnosis
from regtriage.errors import AgentLoopError
from regtriage.tools import git_blame, git_log, grep_source, read_log_lines

SUBMIT_DIAGNOSIS = "submit_diagnosis"
READ_LOG_LINES = "read_log_lines"
GREP_SOURCE = "grep_source"
GIT_BLAME = "git_blame"
GIT_LOG = "git_log"

# Server-side regex kill clock. The model never sees or sets this: the
# timeout is fixed here so a compromised model cannot stretch it.
SERVER_REGEX_TIMEOUT_SECONDS = 5.0


class ReadLogArgs(BaseModel):
    """Validated arguments for the read_log_lines tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    start_line: int = Field(default=1, ge=1)
    num_lines: int = Field(default=50, ge=1)


class GrepArgs(BaseModel):
    """Validated arguments for the grep_source tool.

    `regex_timeout_seconds` is deliberately absent: the kill clock is a
    server-side constant (SERVER_REGEX_TIMEOUT_SECONDS), never a
    model-controlled argument.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: str = Field(min_length=1)
    path_prefix: str | None = None
    max_results: int = Field(default=50, ge=1)
    fixed_strings: bool = True


class BlameArgs(BaseModel):
    """Validated arguments for the git_blame tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class LogArgs(BaseModel):
    """Validated arguments for the git_log tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str | None = None
    max_count: int = Field(default=20, ge=1)


def _schema(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """Build one Anthropic tool definition from hand-written JSON schema."""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def agent_tool_schemas() -> list[dict[str, Any]]:
    """Return the five tool definitions, including submit_diagnosis."""
    submit_schema = Diagnosis.model_json_schema()
    return [
        _schema(
            READ_LOG_LINES,
            "Read numbered lines from a sim log or text file inside the workspace.",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "default": 1},
                "num_lines": {"type": "integer", "default": 50},
            },
            ["path"],
        ),
        _schema(
            GREP_SOURCE,
            "Search workspace files for a fixed string (default) or regex with "
            "fixed_strings=false; returns path:line:text hits.",
            {
                "pattern": {"type": "string"},
                "path_prefix": {"type": "string"},
                "max_results": {"type": "integer", "default": 50},
                "fixed_strings": {"type": "boolean", "default": True},
            },
            ["pattern"],
        ),
        _schema(
            GIT_BLAME,
            "Blame a line range of a tracked file; returns line, sha, author, text.",
            {
                "path": {"type": "string"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
            },
            ["path", "line_start", "line_end"],
        ),
        _schema(
            GIT_LOG,
            "List recent commits, optionally touching one file; newest first.",
            {
                "path": {"type": "string"},
                "max_count": {"type": "integer", "default": 20},
            },
            [],
        ),
        {
            "name": SUBMIT_DIAGNOSIS,
            "description": (
                "Submit the final per-cluster diagnosis. Call exactly once, "
                "when evidence has been gathered. This is the only way to finish."
            ),
            "input_schema": submit_schema,
        },
    ]


class ToolRuntime:
    """Bind tools to a workspace root; dispatch returns raw (unredacted) text."""

    def __init__(self, root: Path, git_timeout_seconds: float = 30.0) -> None:
        self._root = root
        self._git_timeout_seconds = git_timeout_seconds

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Run one named tool; domain errors propagate for is_error results."""
        if name == READ_LOG_LINES:
            read_args = ReadLogArgs.model_validate(args)
            lines = read_log_lines(
                self._root, read_args.path, read_args.start_line, read_args.num_lines
            )
            return "\n".join(lines)
        if name == GREP_SOURCE:
            grep_args = GrepArgs.model_validate(args)
            hits = grep_source(
                self._root,
                grep_args.pattern,
                grep_args.path_prefix,
                grep_args.max_results,
                grep_args.fixed_strings,
                SERVER_REGEX_TIMEOUT_SECONDS,
            )
            return "\n".join(f"{hit.path}:{hit.line}:{hit.text}" for hit in hits)
        if name == GIT_BLAME:
            blame_args = BlameArgs.model_validate(args)
            rows = git_blame(
                self._root,
                blame_args.path,
                blame_args.line_start,
                blame_args.line_end,
                self._git_timeout_seconds,
            )
            return "\n".join(f"{row.line} {row.sha} {row.author}: {row.text}" for row in rows)
        if name == GIT_LOG:
            log_args = LogArgs.model_validate(args)
            commits = git_log(
                self._root, log_args.path, log_args.max_count, self._git_timeout_seconds
            )
            return "\n".join(
                f"{commit.sha} {commit.date} {commit.author} {commit.subject}" for commit in commits
            )
        raise AgentLoopError(f"unknown tool requested by model: {name}")
