"""Memory-bounded helpers for large Knowledge Cloud artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO


class _JSONStream:
    def __init__(self, handle: TextIO, chunk_size: int) -> None:
        self.handle = handle
        self.chunk_size = chunk_size
        self.buffer = ""
        self.pos = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def _refill(self, *, preserve_from: int | None = None) -> bool:
        if preserve_from is None:
            preserve_from = self.pos
        self.buffer = self.buffer[preserve_from:]
        self.pos -= preserve_from
        chunk = self.handle.read(self.chunk_size)
        if not chunk:
            self.eof = True
            return False
        self.buffer += chunk
        return True

    def skip_whitespace(self) -> None:
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buffer) or self.eof:
                return
            self._refill()

    def take(self) -> str:
        self.skip_whitespace()
        if self.pos >= len(self.buffer):
            raise ValueError("unexpected end of JSON")
        value = self.buffer[self.pos]
        self.pos += 1
        return value

    def peek(self) -> str:
        self.skip_whitespace()
        if self.pos >= len(self.buffer):
            raise ValueError("unexpected end of JSON")
        return self.buffer[self.pos]

    def decode_value(self) -> Any:
        self.skip_whitespace()
        start = self.pos
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
                self.pos = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self._refill(preserve_from=start)
                start = 0


def count_json_collection(path: str | Path, *, chunk_size: int = 1024 * 1024) -> int:
    """Count a top-level JSON array or object without loading it into memory."""
    with Path(path).open("r", encoding="utf-8") as handle:
        stream = _JSONStream(handle, chunk_size)
        opener = stream.take()
        if opener not in {"[", "{"}:
            raise ValueError("JSON collection must be a top-level array or object")
        closer = "]" if opener == "[" else "}"
        count = 0
        if stream.peek() == closer:
            stream.take()
            return 0

        while True:
            if opener == "{":
                key = stream.decode_value()
                if not isinstance(key, str):
                    raise ValueError("JSON object key must be a string")
                if stream.take() != ":":
                    raise ValueError("expected ':' after JSON object key")
            stream.decode_value()
            count += 1
            separator = stream.take()
            if separator == closer:
                return count
            if separator != ",":
                raise ValueError(f"expected ',' or {closer!r} in JSON collection")
