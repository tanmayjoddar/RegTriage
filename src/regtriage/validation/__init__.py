"""Machine-checked evidence validation for agent citations."""

from regtriage.validation.evidence import Evidence, EvidenceKind
from regtriage.validation.validator import normalize_quote, validate_evidence

__all__ = ["Evidence", "EvidenceKind", "normalize_quote", "validate_evidence"]
