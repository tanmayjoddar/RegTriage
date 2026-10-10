"""Live Anthropic and scripted Replay LLM clients (dependency injection)."""

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import SecretStr

from regtriage.agent.protocol import (
    LlmRequest,
    LlmResponse,
    TextBlock,
    ToolUseBlock,
)
from regtriage.errors import AgentLoopError, ConfigurationError

_DEFAULT_MAX_OUTPUT_TOKENS = 2048
_DEFAULT_TIMEOUT_SECONDS = 60.0

# Factory building the low-level SDK client from (api_key, timeout). Tests
# inject a recording fake; production passes the real anthropic.Anthropic.
ClientFactory = Callable[[str, float], Any]


def _default_client_factory(api_key: str, timeout_seconds: float) -> Any:
    """Build the real Anthropic SDK client. Imported lazily for testability."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)


class ReplayClient:
    """Serve scripted responses in order and record every request sent."""

    def __init__(self, script: Sequence[LlmResponse]) -> None:
        self._script = list(script)
        self._requests: list[LlmRequest] = []
        self._cursor = 0

    @property
    def requests(self) -> list[LlmRequest]:
        """Return a copy of every request received so far."""
        return list(self._requests)

    def create_message(self, request: LlmRequest) -> LlmResponse:
        """Return the next scripted response; fail loudly when exhausted."""
        self._requests.append(request)
        if self._cursor >= len(self._script):
            raise AgentLoopError(
                "replay script exhausted: the model asked for another turn",
                steps_taken=self._cursor,
            )
        response = self._script[self._cursor]
        self._cursor += 1
        return response


class AnthropicClient:
    """Thin translator between our protocol types and the Anthropic SDK."""

    def __init__(
        self,
        api_key: SecretStr,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        client_factory: ClientFactory | None = None,
    ) -> None:
        key = api_key.get_secret_value()
        if not key.strip():
            raise ConfigurationError(
                "Anthropic API key is empty",
                parameter_name="ANTHROPIC_API_KEY",
            )
        if timeout_seconds <= 0:
            raise ConfigurationError(
                "timeout_seconds must be positive",
                parameter_name="timeout_seconds",
            )
        # The secret value travels only into the SDK client constructor and
        # never into logs, audit records, or error messages.
        factory = client_factory if client_factory is not None else _default_client_factory
        self._client = factory(key, timeout_seconds)
        self._max_output_tokens = max_output_tokens

    def create_message(self, request: LlmRequest) -> LlmResponse:
        """Translate, call with SDK-level timeout, translate back."""
        messages = [
            {"role": message.role, "content": [block.model_dump() for block in message.content]}
            for message in request.messages
        ]
        try:
            raw = self._client.messages.create(
                model=request.model,
                max_tokens=self._max_output_tokens,
                system=request.system,
                messages=messages,
                tools=request.tools,
                tool_choice=request.tool_choice or {"type": "auto"},
            )
        except Exception as exc:
            raise AgentLoopError(f"Anthropic API call failed: {exc}") from exc
        return _translate_response(raw)


def _translate_response(raw: Any) -> LlmResponse:
    """Convert an SDK response into protocol blocks; reject unknown shapes."""
    blocks: list[TextBlock | ToolUseBlock] = []
    for block in getattr(raw, "content", []) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            blocks.append(TextBlock(text=str(getattr(block, "text", ""))))
        elif kind == "tool_use":
            args = getattr(block, "input", None) or {}
            blocks.append(
                ToolUseBlock(
                    id=str(getattr(block, "id", "")),
                    name=str(getattr(block, "name", "")),
                    input=dict(args),
                )
            )
        else:
            raise AgentLoopError(f"unsupported response block type: {kind!r}")
    usage = getattr(raw, "usage", None)
    return LlmResponse(
        content=blocks,
        stop_reason=str(getattr(raw, "stop_reason", "") or ""),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
    )
