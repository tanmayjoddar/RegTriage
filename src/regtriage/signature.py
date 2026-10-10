"""Failure-message normalization and signature clustering.

Normalization replaces run-specific details (addresses, numbers, timestamps,
paths, instance indices) with stable placeholders so the same root cause
produces the same signature across runs. All patterns are flat character
classes without nesting, so matching is linear and cannot backtrack
catastrophically.
"""

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field

from regtriage.errors import ConfigurationError
from regtriage.parsing import Failure

_VLIT_RE = re.compile(r"\b\d+'[bBdDhH][0-9a-fA-FxXzZ?_]+")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_TIME_RE = re.compile(r"\b\d{1,3}:\d{2}:\d{2}(\.\d+)?\b")
_SIMTIME_RE = re.compile(r"\b\d+(\.\d+)?\s?(?:ns|us|ms|ps|fs)\b")
_INDEX_RE = re.compile(r"\[\d+\]")
_PATH_RE = re.compile(r"[A-Za-z0-9_.~\-]*[\\/][A-Za-z0-9_.~\/\\\-]*")
_NUMBER_RE = re.compile(r"\b\d+\b")
_WS_RE = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    """Replace run-specific details with placeholders; idempotent."""
    text = message.lower()
    text = _VLIT_RE.sub("<vlit>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _TIME_RE.sub("<time>", text)
    text = _SIMTIME_RE.sub("<time>", text)
    text = _INDEX_RE.sub("[n]", text)
    text = _PATH_RE.sub("<path>", text)
    text = _NUMBER_RE.sub("<n>", text)
    return _WS_RE.sub(" ", text).strip()


def signature_of(message: str) -> str:
    """Return the stable sha256 hex signature of a failure message."""
    return hashlib.sha256(normalize_message(message).encode("utf-8")).hexdigest()


def jaccard(first: set[str], second: set[str]) -> float:
    """Return token-set Jaccard similarity; two empty sets score 1.0."""
    union = first | second
    if not union:
        return 1.0
    return len(first & second) / len(union)


class Cluster(BaseModel):
    """Failures sharing one root cause: representative signature plus members."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    members: list[Failure] = Field(min_length=1)


def cluster_failures(failures: list[Failure], threshold: float = 0.75) -> list[Cluster]:
    """Group failures by exact signature, then merge near-duplicates.

    Near-duplicates merge greedily when the Jaccard similarity of their
    normalized token sets reaches `threshold`. Exact groups are visited in
    sorted signature order, so the result does not depend on input order.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ConfigurationError(
            f"threshold must be between 0.0 and 1.0, got {threshold}",
            parameter_name="threshold",
        )
    if not failures:
        return []
    exact: dict[str, list[Failure]] = {}
    for failure in failures:
        exact.setdefault(signature_of(failure.message), []).append(failure)
    merged: list[list[tuple[str, list[Failure]]]] = []
    token_sets: list[set[str]] = []
    for sig, members in sorted(exact.items()):
        tokens = set(normalize_message(members[0].message).split())
        placed = False
        for i, existing in enumerate(token_sets):
            if jaccard(tokens, existing) >= threshold:
                merged[i].append((sig, members))
                token_sets[i] = existing | tokens
                placed = True
                break
        if not placed:
            merged.append([(sig, members)])
            token_sets.append(set(tokens))
    clusters: list[Cluster] = []
    for index, group in enumerate(merged, start=1):
        members_all = [failure for _, group_members in group for failure in group_members]
        clusters.append(
            Cluster(
                cluster_id=f"cluster-{index:03d}",
                signature=group[0][0],
                members=members_all,
            )
        )
    return clusters
