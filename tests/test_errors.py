"""Tests for explicit custom exception hierarchy."""

from regtriage.errors import (
    AgentLoopError,
    ConfigurationError,
    ExecutionError,
    ParsingError,
    RedactionError,
    RegTriageError,
    SandboxViolationError,
    ValidationError,
)


def test_base_regtriage_error_attributes_and_dict() -> None:
    err = RegTriageError("Operation failed", {"code": 42, "retry": False})
    assert err.message == "Operation failed"
    assert err.details == {"code": 42, "retry": False}
    assert "code=42" in str(err)
    assert "retry=False" in str(err)

    as_dict = err.to_dict()
    assert as_dict["error_type"] == "RegTriageError"
    assert as_dict["message"] == "Operation failed"
    assert as_dict["details"] == {"code": 42, "retry": False}


def test_base_regtriage_error_empty_details() -> None:
    err = RegTriageError("Plain error")
    assert err.details == {}
    assert str(err) == "Plain error"


def test_configuration_error() -> None:
    err = ConfigurationError("Invalid path", parameter_name="REGTRIAGE_REPO_PATH")
    assert err.parameter_name == "REGTRIAGE_REPO_PATH"
    assert err.details["parameter_name"] == "REGTRIAGE_REPO_PATH"
    assert "parameter_name='REGTRIAGE_REPO_PATH'" in str(err)


def test_execution_error() -> None:
    err = ExecutionError(
        message="Command timed out",
        command=["make", "sim"],
        returncode=124,
        stderr="Timeout after 30s",
        timed_out=True,
    )
    assert err.command == ["make", "sim"]
    assert err.returncode == 124
    assert err.stderr == "Timeout after 30s"
    assert err.timed_out is True
    assert err.details["timed_out"] is True
    assert err.details["command"] == ["make", "sim"]


def test_parsing_error() -> None:
    err = ParsingError(
        message="Malformed XML element",
        source_path="/sim/results.xml",
        line_number=45,
        raw_content="<failure message='assert",
    )
    assert err.source_path == "/sim/results.xml"
    assert err.line_number == 45
    assert err.raw_content == "<failure message='assert"
    assert err.details["line_number"] == 45


def test_sandbox_violation_error() -> None:
    err = SandboxViolationError(
        message="Access denied: path escapes workspace root",
        attempted_target="../../etc/shadow",
        allowed_root="/workspace",
        violation_type="path_traversal",
    )
    assert err.attempted_target == "../../etc/shadow"
    assert err.allowed_root == "/workspace"
    assert err.violation_type == "path_traversal"
    assert err.details["violation_type"] == "path_traversal"


def test_validation_error() -> None:
    err = ValidationError(
        message="Quote mismatch at lines 10-12",
        citation_kind="source",
        citation_ref="rtl/pcie_tlp.v",
        reason="Normalized quote text was not found in specified file lines",
    )
    assert err.citation_kind == "source"
    assert err.citation_ref == "rtl/pcie_tlp.v"
    assert err.reason == "Normalized quote text was not found in specified file lines"
    assert err.details["citation_kind"] == "source"


def test_agent_loop_error() -> None:
    err = AgentLoopError(
        message="Step ceiling exceeded without diagnosis",
        cluster_id="cluster_01",
        steps_taken=8,
        token_count=12500,
    )
    assert err.cluster_id == "cluster_01"
    assert err.steps_taken == 8
    assert err.token_count == 12500
    assert err.details["steps_taken"] == 8


def test_redaction_error() -> None:
    err = RedactionError("Pattern compilation failure", pattern_name="regex_custom")
    assert err.pattern_name == "regex_custom"
    assert err.details["pattern_name"] == "regex_custom"


def test_inheritance_hierarchy() -> None:
    classes = [
        ConfigurationError,
        ExecutionError,
        ParsingError,
        SandboxViolationError,
        ValidationError,
        AgentLoopError,
        RedactionError,
    ]
    for cls in classes:
        instance = cls("test message")
        assert isinstance(instance, RegTriageError)
        assert isinstance(instance, Exception)
