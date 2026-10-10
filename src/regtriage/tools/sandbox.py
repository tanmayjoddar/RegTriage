"""Path confinement and resource caps for the read-only triage tools."""

from pathlib import Path

from regtriage.errors import ConfigurationError, SandboxViolationError

_DEFAULT_MAX_LINES = 200
_DEFAULT_MAX_BYTES = 65_536
_DEFAULT_MAX_RESULTS = 50
_MAX_FILE_BYTES = 128_000_000


def resolve_root(root: Path) -> Path:
    """Resolve the allowed root; refuse missing or non-directory roots."""
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ConfigurationError(
            f"tool root is not a directory: {root}",
            parameter_name="root",
        )
    return resolved


def resolve_within_root(root: Path, target: str) -> Path:
    """Resolve `target` against `root`, rejecting escapes.

    `Path.resolve()` follows symlinks and collapses `..`, so comparing the
    resolved target against the resolved root rejects symlink escapes, `..`
    traversal, and absolute paths outside the root in one check. A target
    that stays inside (e.g. `a/../b`) is allowed.
    """
    resolved_root = resolve_root(root)
    resolved = (resolved_root / target).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise SandboxViolationError(
            f"path escapes the allowed root: {target}",
            attempted_target=target,
            allowed_root=str(resolved_root),
            violation_type="path_traversal",
        )
    return resolved
