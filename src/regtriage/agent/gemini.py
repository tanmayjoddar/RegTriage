"""Gemini (google-genai SDK) LLM client implementing the LlmClient protocol.

SDK usage verified 2026-10-10 against google-genai 2.29.0 (installed) and
https://ai.google.dev/gemini-api/docs/models (GA default for new agent work
is Gemini 3.8 Flash) plus function-calling docs (ANY mode +
allowed_function_names to force a tool call; automatic function calling
disabled so the loop — not the SDK — drives tool execution).
"""

import random
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import SecretStr

from regtriage.agent.diagnosis import Diagnosis
from regtriage.agent.protocol import (
    ConversationMessage,
    LlmRequest,
    LlmResponse,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from regtriage.agent.tooling import SUBMIT_DIAGNOSIS, agent_tool_schemas
from regtriage.config import DEFAULT_GEMINI_MODEL_ID
from regtriage.errors import AgentLoopError, ConfigurationError

__all__ = ["DEFAULT_GEMINI_MODEL_ID", "GeminiClient", "flatten_diagnosis_schema"]

_GEMINI_MAX_OUTPUT_TOKENS = 2048
_GEMINI_TIMEOUT_SECONDS = 60.0
_GEMINI_MAX_RETRIES = 3
_GEMINI_BACKOFF_BASE_SECONDS = 1.0
_GEMINI_BACKOFF_CAP_SECONDS = 30.0
_RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})

# Factory building the low-level SDK client from (api_key, timeout). Tests
# inject a recording fake; production passes the real google.genai.Client.
GeminiClientFactory = Callable[[str, float], Any]
Sleeper = Callable[[float], None]


def _default_gemini_factory(api_key: str, timeout_seconds: float) -> Any:
    """Build the real google-genai client. Imported lazily for testability."""
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000))
    )


def flatten_diagnosis_schema() -> dict[str, Any]:
    """Inline pydantic $defs/$ref into a plain JSON schema for Gemini.

    Function declarations accept a JSON-schema subset without references,
    so every `$ref: #/$defs/<Name>` is replaced by the referenced
    definition (recursively). Anything unresolvable raises ConfigurationError
    instead of shipping a schema the API would reject.
    """

    def _resolve(node: Any, defs: Mapping[str, Any]) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
                    raise ConfigurationError(
                        f"unsupported schema $ref for Gemini: {ref!r}",
                        parameter_name="model_id",
                    )
                name = ref[len("#/$defs/") :]
                if name not in defs:
                    raise ConfigurationError(
                        f"missing schema $def for Gemini: {name!r}",
                        parameter_name="model_id",
                    )
                extra = {key: _resolve(value, defs) for key, value in node.items() if key != "$ref"}
                resolved = _resolve(defs[name], defs)
                if isinstance(resolved, dict):
                    return {**resolved, **extra}
                return resolved
            return {key: _resolve(value, defs) for key, value in node.items()}
        if isinstance(node, list):
            return [_resolve(item, defs) for item in node]
        return node

    raw = Diagnosis.model_json_schema()
    defs = raw.get("$defs", {})
    if not isinstance(defs, dict):
        raise ConfigurationError("Diagnosis schema has no $defs table", parameter_name="model_id")
    flat = _resolve({key: value for key, value in raw.items() if key != "$defs"}, defs)
    if not isinstance(flat, dict):
        raise ConfigurationError("Diagnosis schema did not flatten to an object", parameter_name="model_id")
    return flat


def _gemini_tools() -> list[Any]:
    """Translate our five tool schemas into Gemini function declarations."""
    from google.genai import types

    declarations: list[Any] = []
    for schema in agent_tool_schemas():
        if schema["name"] == SUBMIT_DIAGNOSIS:
            parameters: dict[str, Any] = flatten_diagnosis_schema()
            description = str(schema["description"])
        else:
            input_schema = schema["input_schema"]
            parameters = {
                "type": "object",
                "properties": dict(input_schema["properties"]),
                "required": list(input_schema.get("required", [])),
            }
            description = str(schema["description"])
        declarations.append(
            types.FunctionDeclaration(
                name=schema["name"],
                description=description,
                parameters_json_schema=parameters,
            )
        )
    return declarations


def _tool_choice_to_config(tool_choice: dict[str, Any]) -> Any:
    """Map our tool_choice onto Gemini's function-calling config.

    Forced submit_diagnosis becomes mode ANY restricted to that one
    function; anything else stays AUTO.
    """
    from google.genai import types

    if tool_choice.get("type") == "tool":
        names = [tool_choice["name"]] if tool_choice.get("name") else [SUBMIT_DIAGNOSIS]
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=list(names),
            )
        )
    return types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.AUTO,
        )
    )


def _to_gemini_contents(request: LlmRequest) -> list[Any]:
    """Translate messages: user/model roles, text/call/response parts.

    ToolResultBlocks need their function name, which the protocol stores
    only on the matching ToolUseBlock: map ids from the whole request first.
    """
    from google.genai import types

    names_by_id: dict[str, str] = {}
    for message in request.messages:
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                names_by_id[block.id] = block.name
    contents: list[Any] = []
    for message in request.messages:
        if message.role == "assistant":
            parts: list[Any] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    p = types.Part.from_text(text=block.text)
                    if block.provider_state is not None:
                        p.thought_signature = block.provider_state
                    parts.append(p)
                elif isinstance(block, ToolUseBlock):
                    p = types.Part.from_function_call(name=block.name, args=dict(block.input))
                    if block.id and p.function_call is not None:
                        p.function_call.id = block.id
                    if block.provider_state is not None:
                        p.thought_signature = block.provider_state
                    parts.append(p)
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        else:
            user_parts: list[Any] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    user_parts.append(types.Part.from_text(text=block.text))
                elif isinstance(block, ToolResultBlock):
                    name = names_by_id.get(block.tool_use_id, "unknown")
                    part = types.Part.from_function_response(
                        name=name, response={"result": block.content}
                    )
                    if part.function_response is not None and block.tool_use_id:
                        part.function_response.id = block.tool_use_id
                    user_parts.append(part)
            if user_parts:
                contents.append(types.Content(role="user", parts=user_parts))
    return contents


def _from_gemini_response(
    raw: Any, id_generator: Callable[[], str] | None = None
) -> LlmResponse:
    """Translate candidates/usage back; reject unknown part shapes."""
    blocks: list[TextBlock | ToolUseBlock] = []
    candidates: Sequence[Any] = getattr(raw, "candidates", None) or []
    content: Any = candidates[0].content if candidates else None
    parts: Sequence[Any] = getattr(content, "parts", None) or []
    for index, part in enumerate(parts):
        call = getattr(part, "function_call", None)
        signature = getattr(part, "thought_signature", None)
        if signature is None and call is not None:
            signature = getattr(call, "thought_signature", None)
        if signature is None:
            signature = getattr(part, "signature", None)
        if call is not None and getattr(call, "name", None):
            args = getattr(call, "args", None) or {}
            raw_id = getattr(call, "id", None)
            if raw_id:
                call_id = str(raw_id)
            elif id_generator is not None:
                call_id = id_generator()
            else:
                call_id = f"call-{uuid.uuid4().hex[:12]}"
            blocks.append(
                ToolUseBlock(
                    id=str(call_id),
                    name=str(call.name),
                    input=dict(args),
                    provider_state=signature,
                )
            )
        elif getattr(part, "text", None) is not None:
            blocks.append(
                TextBlock(
                    text=str(getattr(part, "text") or ""),
                    provider_state=signature,
                )
            )
        else:
            raise AgentLoopError(f"unsupported Gemini part shape at index {index!r}")
    usage = getattr(raw, "usage_metadata", None)
    stop_reason = ""
    if candidates:
        stop_reason = str(getattr(candidates[0], "finish_reason", "") or "")
    return LlmResponse(
        content=blocks,
        stop_reason=stop_reason,
        input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
    )


def _status_code(exc: BaseException) -> int | None:
    """Extract an HTTP status from an SDK error, else None."""
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _retry_delay_hint(exc: BaseException) -> float | None:
    """Honor a server retry hint (RetryInfo retryDelay), else None."""
    payload = getattr(exc, "details", None)
    if not isinstance(payload, dict):
        payload = getattr(exc, "response_json", None)
    if not isinstance(payload, dict):
        return None
    inner = payload.get("error")
    error = inner if isinstance(inner, dict) else payload
    details = error.get("details")
    if not isinstance(details, list):
        details = payload.get("details")
    if not isinstance(details, list):
        return None
    for entry in details:
        if not isinstance(entry, dict):
            continue
        raw_delay = entry.get("retryDelay")
        if isinstance(raw_delay, str) and raw_delay.endswith("s"):
            try:
                return max(0.0, float(raw_delay[:-1]))
            except ValueError:
                continue
    return None


class GeminiClient:
    """Thin translator between our protocol types and the google-genai SDK."""

    def __init__(
        self,
        api_key: SecretStr,
        timeout_seconds: float = _GEMINI_TIMEOUT_SECONDS,
        max_output_tokens: int = _GEMINI_MAX_OUTPUT_TOKENS,
        max_retries: int = _GEMINI_MAX_RETRIES,
        client_factory: GeminiClientFactory | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        key = api_key.get_secret_value()
        if not key.strip():
            raise ConfigurationError(
                "Gemini API key is empty",
                parameter_name="GEMINI_API_KEY",
            )
        if timeout_seconds <= 0:
            raise ConfigurationError(
                "timeout_seconds must be positive",
                parameter_name="timeout_seconds",
            )
        if max_output_tokens <= 0:
            raise ConfigurationError(
                "max_output_tokens must be positive",
                parameter_name="max_output_tokens",
            )
        if max_retries < 0:
            raise ConfigurationError(
                "max_retries must not be negative",
                parameter_name="max_retries",
            )
        # The secret value travels only into the SDK client constructor and
        # never into logs, audit records, or error messages.
        factory = client_factory if client_factory is not None else _default_gemini_factory
        self._client = factory(key, timeout_seconds)
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        self._sleeper = sleeper if sleeper is not None else time.sleep
        self._call_counter = 0

    def _next_tool_call_id(self) -> str:
        self._call_counter += 1
        return f"call-{self._call_counter}"

    def _models(self) -> Any:
        return self._client.models

    def create_message(self, request: LlmRequest) -> LlmResponse:
        """Translate, call with retries on 429/5xx, translate back."""
        from google.genai import types

        contents = _to_gemini_contents(request)
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            tools=[types.Tool(function_declarations=_gemini_tools())],
            tool_config=_tool_choice_to_config(request.tool_choice),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=self._max_output_tokens,
        )
        attempt = 0
        while True:
            try:
                raw = self._models().generate_content(
                    model=request.model, contents=contents, config=config
                )
            except Exception as exc:
                code = _status_code(exc)
                if code not in _RETRYABLE_CODES or attempt >= self._max_retries:
                    raise AgentLoopError(f"Gemini API call failed: {exc}") from exc
                hint = _retry_delay_hint(exc)
                if hint is not None:
                    wait = min(hint, _GEMINI_BACKOFF_CAP_SECONDS)
                else:
                    wait = min(
                        _GEMINI_BACKOFF_BASE_SECONDS * (2.0**attempt)
                        + random.uniform(0.0, 0.5),  # nosec B311: jitter only, not security use.
                        _GEMINI_BACKOFF_CAP_SECONDS,
                    )
                self._sleeper(wait)
                attempt += 1
                continue
            return _from_gemini_response(raw, id_generator=self._next_tool_call_id)
