"""Path confinement and resource caps for the read-only triage tools."""

from pathlib import Path

from regtriage.errors import ConfigurationError, SandboxViolationError

_DEFAULT_MAX_LINES = 200
_DEFAULT_MAX_BYTES = 65_536
_DEFAULT_MAX_RESULTS = 50
_MAX_FILE_BYTES = 128_000_000

# Never servable through read tools, whatever the root: version-control
# internals (file or directory, at any depth), environment files, and
# private key material. Dotfiles outside this list (.gitignore, configs)
# stay readable.
_DENIED_DIR_PARTS = frozenset({".git"})
_DENIED_BASENAMES = frozenset({".env"})
_DENIED_BASENAME_PREFIXES = (".env.",)
_DENIED_PRIVATE_NAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
_DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def resolve_root(root: Path) -> Path:
    """Resolve the allowed root; refuse missing or non-directory roots."""
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ConfigurationError(
            f"tool root is not a directory: {root}",
            parameter_name="root",
        )
    return resolved


def denied_name_reason(candidate: Path) -> str | None:
    """Return why a path is unservable, or None when its name is allowed.

    Pure name rules, root-independent: any `.git` part (file or directory,
    e.g. worktree pointers), `.env` files, and private key material.
    """
    if any(part in _DENIED_DIR_PARTS for part in candidate.parts):
        return ".git internals are off limits to read tools"
    name = candidate.name
    if name in _DENIED_BASENAMES or name.startswith(_DENIED_BASENAME_PREFIXES):
        return "environment files are off limits to read tools"
    if name in _DENIED_PRIVATE_NAMES or name.endswith(_DENIED_SUFFIXES):
        return "private key material is off limits to read tools"
    return None


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
    reason = denied_name_reason(resolved)
    if reason is not None:
        raise SandboxViolationError(
            f"{reason}: {target}",
            attempted_target=target,
            allowed_root=str(resolved_root),
            violation_type="denied_name",
        )
    return resolved
