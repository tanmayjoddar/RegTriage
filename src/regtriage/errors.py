"""Explicit custom exception hierarchy for RegTriage."""

from typing import Any


class RegTriageError(Exception):
    """Base exception for all domain errors within RegTriage."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details) if details is not None else {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize error information to a dictionary representation."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v!r}" for k, v in sorted(self.details.items()))
            return f"{self.message} ({detail_str})"
        return self.message


class ConfigurationError(RegTriageError):
    """Raised when configuration validation or environment resolution fails."""

    def __init__(
        self,
        message: str,
        parameter_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if parameter_name is not None:
            payload["parameter_name"] = parameter_name
        super().__init__(message, payload)
        self.parameter_name = parameter_name


class ExecutionError(RegTriageError):
    """Raised when process or runner execution fails or times out."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
        timed_out: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if command is not None:
            payload["command"] = list(command)
        if returncode is not None:
            payload["returncode"] = returncode
        if stderr is not None:
            payload["stderr"] = stderr
        payload["timed_out"] = timed_out
        super().__init__(message, payload)
        self.command = list(command) if command is not None else None
        self.returncode = returncode
        self.stderr = stderr
        self.timed_out = timed_out


class ParsingError(RegTriageError):
    """Raised when simulation results, XML, or log parsing encounters invalid formats."""

    def __init__(
        self,
        message: str,
        source_path: str | None = None,
        line_number: int | None = None,
        raw_content: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if source_path is not None:
            payload["source_path"] = source_path
        if line_number is not None:
            payload["line_number"] = line_number
        if raw_content is not None:
            payload["raw_content"] = raw_content[:200]
        super().__init__(message, payload)
        self.source_path = source_path
        self.line_number = line_number
        self.raw_content = raw_content


class SandboxViolationError(RegTriageError):
    """Raised when an operation violates path confinement, size caps, or safety limits."""

    def __init__(
        self,
        message: str,
        attempted_target: str | None = None,
        allowed_root: str | None = None,
        violation_type: str = "path_traversal",
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if attempted_target is not None:
            payload["attempted_target"] = attempted_target
        if allowed_root is not None:
            payload["allowed_root"] = allowed_root
        payload["violation_type"] = violation_type
        super().__init__(message, payload)
        self.attempted_target = attempted_target
        self.allowed_root = allowed_root
        self.violation_type = violation_type


class ValidationError(RegTriageError):
    """Raised when evidence verification fails against actual repository contents."""

    def __init__(
        self,
        message: str,
        citation_kind: str | None = None,
        citation_ref: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if citation_kind is not None:
            payload["citation_kind"] = citation_kind
        if citation_ref is not None:
            payload["citation_ref"] = citation_ref
        if reason is not None:
            payload["reason"] = reason
        super().__init__(message, payload)
        self.citation_kind = citation_kind
        self.citation_ref = citation_ref
        self.reason = reason


class AgentLoopError(RegTriageError):
    """Raised when the triage agent loop encounters unrecoverable conditions or budget limits."""

    def __init__(
        self,
        message: str,
        cluster_id: str | None = None,
        steps_taken: int = 0,
        token_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if cluster_id is not None:
            payload["cluster_id"] = cluster_id
        payload["steps_taken"] = steps_taken
        payload["token_count"] = token_count
        super().__init__(message, payload)
        self.cluster_id = cluster_id
        self.steps_taken = steps_taken
        self.token_count = token_count


class RedactionError(RegTriageError):
    """Raised when secret detection or text sanitization encounters invalid states."""

    def __init__(
        self,
        message: str,
        pattern_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details) if details is not None else {}
        if pattern_name is not None:
            payload["pattern_name"] = pattern_name
        super().__init__(message, payload)
        self.pattern_name = pattern_name


class BudgetExceeded(AgentLoopError):  # noqa: N818 - name mandated by the cost-guard contract.
    """Raised before sending an LLM call that would breach a call/cost ceiling."""

    def __init__(
        self,
        message: str,
        cluster_id: str | None = None,
        steps_taken: int = 0,
        token_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            cluster_id=cluster_id,
            steps_taken=steps_taken,
            token_count=token_count,
            details=details,
        )
