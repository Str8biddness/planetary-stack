"""Memory-bounded helpers for large JSON-array artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_json_array(path: str | Path, *, chunk_size: int = 1024 * 1024) -> Iterator[Any]:
    """Yield values from a top-level JSON array without loading it all at once."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    decoder = json.JSONDecoder()
    with Path(path).open("r", encoding="utf-8") as handle:
        buffer = ""
        position = 0
        eof = False

        def read_more() -> None:
            nonlocal buffer, position, eof
            if position:
                buffer = buffer[position:]
                position = 0
            chunk = handle.read(chunk_size)
            if chunk:
                buffer += chunk
            else:
                eof = True

        def skip_whitespace() -> None:
            nonlocal position
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer) or eof:
                    return
                read_more()

        read_more()
        skip_whitespace()
        if position >= len(buffer) or buffer[position] != "[":
            raise ValueError(f"expected a top-level JSON array in {path}")
        position += 1

        first = True
        while True:
            skip_whitespace()
            if position >= len(buffer):
                if eof:
                    raise ValueError(f"unterminated JSON array in {path}")
                read_more()
                continue

            if buffer[position] == "]":
                position += 1
                skip_whitespace()
                if position < len(buffer) or not eof:
                    read_more()
                    skip_whitespace()
                if position < len(buffer):
                    raise ValueError(f"trailing data after JSON array in {path}")
                return

            if not first:
                if buffer[position] != ",":
                    raise ValueError(f"expected ',' between JSON array values in {path}")
                position += 1
                skip_whitespace()

            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                except json.JSONDecodeError as exc:
                    if eof:
                        raise ValueError(f"invalid JSON array in {path}: {exc}") from exc
                    read_more()
                    skip_whitespace()
                    continue
                position = end
                first = False
                yield value
                break


def count_json_array(path: str | Path) -> int:
    """Count top-level array values with bounded memory use."""
    return sum(1 for _ in iter_json_array(path))
