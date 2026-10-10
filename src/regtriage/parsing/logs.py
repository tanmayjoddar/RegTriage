"""Shared helpers for line-oriented log parsers (UVM, Verilator lint)."""

from pathlib import Path

from regtriage.errors import ConfigurationError, ParsingError

DEFAULT_MAX_BYTES = 32_000_000
DEFAULT_MAX_EXCERPT_CHARS = 4000


def read_log_text(path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> list[str]:
    """Read a log file as lines; same guards as the cocotb parser.

    Raises ParsingError for missing/unreadable/oversized/non-UTF-8 files.
    Decodes strictly so mojibake never becomes fake evidence.
    """
    if max_bytes < 1:
        raise ConfigurationError(
            f"max_bytes must be at least 1, got {max_bytes}", parameter_name="max_bytes"
        )
    if not path.is_file():
        raise ParsingError(f"log file does not exist: {path}", source_path=str(path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ParsingError(f"cannot read log file: {path}", source_path=str(path)) from exc
    if len(raw) > max_bytes:
        raise ParsingError(f"log file larger than {max_bytes} bytes: {path}", source_path=str(path))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParsingError(f"log file is not valid UTF-8: {path}", source_path=str(path)) from exc
    return text.splitlines()
