"""SDK-agnostic message and client types for the triage agent loop."""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TextBlock(BaseModel):
    """Plain text content block in either role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"] = "text"
    text: str = ""


class ToolUseBlock(BaseModel):
    """Assistant's request to call one tool with JSON arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tool_use"] = "tool_use"
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """Result delivered back for one tool_use id, optionally an error."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = Field(min_length=1)
    content: str = ""
    is_error: bool = False


class ConversationMessage(BaseModel):
    """One user or assistant turn in the Anthropic Messages shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: list[TextBlock | ToolUseBlock | ToolResultBlock]


class LlmResponse(BaseModel):
    """What the model returned: content blocks, stop reason, token usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: list[TextBlock | ToolUseBlock] = Field(default_factory=list)
    stop_reason: str = ""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class LlmRequest(BaseModel):
    """Everything sent for one model turn; this exact shape is audit-logged."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    system: str = ""
    messages: list[ConversationMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: dict[str, Any] = Field(default_factory=dict)


class LlmClient(Protocol):
    """Sends one request, returns one response. Never raises on model output."""

    def create_message(self, request: LlmRequest) -> LlmResponse:
        """Send `request` to the model and return its parsed response."""
        ...
