"""Seeded Verilog mutation operators with recorded ground truth.

Each operator maps one source line to a mutated line (or None when it does
not apply). Mutations are deliberately small syntactic changes — simpler
than real protocol-level PCIe bugs; that limitation is stated in the
generated RESULTS.md, not hidden.
"""

import random
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MutationOperator = Literal[
    "flip_comparison",
    "invert_if",
    "off_by_one_const",
    "off_by_one_width",
    "remove_reset",
    "invert_enable",
]

_EQ_RE = re.compile(r"(?<![=!])==(?!=)")
_NEQ_RE = re.compile(r"(?<![=!])!=(?!=)")
_GT_RE = re.compile(r"(?<![<>=!])>(?![>=])")
_LT_RE = re.compile(r"(?<![<>=!])<(?![<=])")
_IF_RE = re.compile(r"^(\s*)(?:else\s+)?if\s*\((.*)\)\s*(begin)?\s*$")
_NUM_RE = re.compile(r"\b\d+\b")
_WIDTH_RE = re.compile(r"\[(\d+):(\d+)\]")
_RESET_RE = re.compile(r"(?i)\brst\b.*<=")
_ENABLE_RE = re.compile(r"if\s*\(([^()]*(?:\ben\b|\benable\b|\bvalid\b|\bready\b)[^()]*)\)")


class Mutant(BaseModel):
    """One applied mutation: where, how, and the before/after line text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mutant_id: str = Field(min_length=1)
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    operator: MutationOperator
    original: str = ""
    mutated: str = ""


def _flip_comparison(line: str) -> str | None:
    """Flip ==/!= or lone >/ comparisons once per line."""
    if _EQ_RE.search(line):
        return _EQ_RE.sub("!=", line, count=1)
    if _NEQ_RE.search(line):
        return _NEQ_RE.sub("==", line, count=1)
    if _GT_RE.search(line):
        return _GT_RE.sub("<", line, count=1)
    if _LT_RE.search(line):
        return _LT_RE.sub(">", line, count=1)
    return None


def _invert_if(line: str) -> str | None:
    """Wrap a single-line if condition in a negation."""
    match = _IF_RE.match(line.rstrip("\n"))
    if match is None:
        return None
    indent, cond, begin = match.group(1), match.group(2).strip(), match.group(3)
    if not cond or cond.startswith("!"):
        return None
    tail = f" {begin}" if begin else ""
    return f"{indent}if (!({cond})){tail}"


def _off_by_one_const(line: str) -> str | None:
    """Increment the first bare decimal on lines without widths or literals."""
    if "[" in line or "'" in line or "0x" in line.lower():
        return None
    match = _NUM_RE.search(line)
    if match is None:
        return None
    return line[: match.start()] + str(int(match.group()) + 1) + line[match.end() :]


def _off_by_one_width(line: str) -> str | None:
    """Widen the first [MSB:LSB] range by one on the MSB side."""
    match = _WIDTH_RE.search(line)
    if match is None:
        return None
    return (
        line[: match.start()]
        + f"[{int(match.group(1)) + 1}:{match.group(2)}]"
        + line[match.end() :]
    )


def _remove_reset(line: str) -> str | None:
    """Comment out a reset assignment line."""
    if _RESET_RE.search(line) and not line.lstrip().startswith("//"):
        return f"// {line}"
    return None


def _invert_enable(line: str) -> str | None:
    """Negate an enable/valid/ready gate condition."""
    match = _ENABLE_RE.search(line)
    if match is None or match.group(1).strip().startswith("!"):
        return None
    cond = match.group(1).strip()
    return line[: match.start(1)] + f"!({cond})" + line[match.end(1) :]


_MutFn = Callable[[str], str | None]

_OPERATORS: tuple[tuple[MutationOperator, _MutFn], ...] = (
    ("flip_comparison", _flip_comparison),
    ("invert_if", _invert_if),
    ("off_by_one_const", _off_by_one_const),
    ("off_by_one_width", _off_by_one_width),
    ("remove_reset", _remove_reset),
    ("invert_enable", _invert_enable),
)


def generate_mutants(sources: dict[str, str], seed: int, count: int) -> list[Mutant]:
    """Collect every applicable (file, line, operator) site, shuffle by seed,
    and take the first `count` as mutants with stable     `mNNNN` ids."""
    sites: list[tuple[str, int, MutationOperator, str, str]] = []
    for path in sorted(sources):
        for lineno, line in enumerate(sources[path].splitlines(), start=1):
            for operator, mutate in _OPERATORS:
                new_line = mutate(line)
                if new_line is not None and new_line != line:
                    sites.append((path, lineno, operator, line, new_line))
    rng = random.Random(seed)  # nosec B311: seeded reproducibility required; not security use.
    rng.shuffle(sites)
    mutants: list[Mutant] = []
    for index, (path, lineno, operator, original, mutated) in enumerate(sites[:count]):
        mutants.append(
            Mutant(
                mutant_id=f"m{index:04d}",
                file=path,
                line=lineno,
                operator=operator,
                original=original,
                mutated=mutated,
            )
        )
    return mutants


def apply_mutant(source: str, mutant: Mutant) -> str:
    """Return the source with the mutant's line replaced (1-based)."""
    lines = source.splitlines()
    if mutant.line > len(lines):
        raise ValueError(f"mutant line {mutant.line} beyond {len(lines)} lines")
    lines[mutant.line - 1] = mutant.mutated
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")
