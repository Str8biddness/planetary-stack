"""Deterministic bounded Unisync frame encoding."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
from dataclasses import dataclass
from typing import Any

from .contracts import MAX_SAFE_INTEGER
from .errors import DigestMismatchError, FrameTooLargeError, InvalidFrameError

PROTOCOL = "planetary.unisync.transport"
VERSION = 1

FRAME_START = "start"
FRAME_ACK = "ack"
FRAME_CHUNK = "chunk"
FRAME_COMPLETE = "complete"
FRAME_CANCEL = "cancel"
FRAME_ERROR = "error"
VALID_FRAME_TYPES = {FRAME_START, FRAME_ACK, FRAME_CHUNK, FRAME_COMPLETE, FRAME_CANCEL, FRAME_ERROR}

_HEADER_PREFIX = struct.Struct("!I")


def _reject_non_finite_number(value: str) -> None:
    raise InvalidFrameError(f"non-I-JSON frame value {value!r}")


@dataclass(frozen=True, slots=True)
class FrameLimits:
    max_header_bytes: int = 4096
    max_payload_bytes: int = 64 * 1024
    max_frame_bytes: int = 72 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_pending_bytes: int = 512 * 1024
    max_pending_chunks: int = 64


DEFAULT_LIMITS = FrameLimits()


@dataclass(frozen=True, slots=True)
class Frame:
    header: dict[str, Any]
    payload: bytes

    @property
    def frame_type(self) -> str:
        return str(self.header["type"])


def _loads_no_duplicate_keys(payload: bytes) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InvalidFrameError(f"duplicate frame header key {key!r}")
            result[key] = value
        return result

    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=hook,
            parse_constant=_reject_non_finite_number,
        )
    except InvalidFrameError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidFrameError("frame header is not canonical UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise InvalidFrameError("frame header must be a JSON object")
    return decoded


def _validate_header(header: dict[str, Any], payload: bytes, limits: FrameLimits) -> None:
    if header.get("protocol") != PROTOCOL:
        raise InvalidFrameError("unsupported protocol")
    if header.get("version") != VERSION:
        raise InvalidFrameError("unsupported protocol version")
    if header.get("type") not in VALID_FRAME_TYPES:
        raise InvalidFrameError("unsupported frame type")
    payload_length = header.get("payload_length")
    if not isinstance(payload_length, int) or isinstance(payload_length, bool) or payload_length < 0:
        raise InvalidFrameError("payload_length must be a non-negative integer")
    if payload_length > MAX_SAFE_INTEGER:
        raise InvalidFrameError("payload_length exceeds the I-JSON safe integer range")
    if payload_length != len(payload):
        raise InvalidFrameError("payload length does not match frame header")
    if payload_length > limits.max_payload_bytes:
        raise FrameTooLargeError("payload exceeds configured chunk cap")
    if header.get("type") == FRAME_CHUNK and payload_length == 0:
        raise InvalidFrameError("chunk payload must be nonempty")
    if header.get("payload_sha256") != hashlib.sha256(payload).hexdigest():
        raise DigestMismatchError("frame payload digest mismatch")
    offset = header.get("offset", 0)
    sequence = header.get("sequence", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise InvalidFrameError("offset must be a non-negative integer")
    if offset > MAX_SAFE_INTEGER:
        raise InvalidFrameError("offset exceeds the I-JSON safe integer range")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise InvalidFrameError("sequence must be a non-negative integer")
    if sequence > MAX_SAFE_INTEGER:
        raise InvalidFrameError("sequence exceeds the I-JSON safe integer range")
    total_length = header.get("total_length")
    if total_length is not None:
        if not isinstance(total_length, int) or isinstance(total_length, bool) or total_length < 0:
            raise InvalidFrameError("total_length must be a non-negative integer")
        if total_length > MAX_SAFE_INTEGER:
            raise InvalidFrameError("total_length exceeds the I-JSON safe integer range")
        if total_length > limits.max_total_bytes:
            raise FrameTooLargeError("total_length exceeds configured cap")
    if offset + payload_length > limits.max_total_bytes:
        raise FrameTooLargeError("frame offset and length exceed configured total cap")


def encode_frame(
    frame_type: str,
    *,
    payload: bytes = b"",
    sequence: int = 0,
    offset: int = 0,
    total_length: int | None = None,
    context: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
    limits: FrameLimits = DEFAULT_LIMITS,
) -> bytes:
    if frame_type not in VALID_FRAME_TYPES:
        raise InvalidFrameError("unsupported frame type")
    if not isinstance(payload, bytes):
        raise InvalidFrameError("payload must be bytes")
    header: dict[str, object] = {
        "protocol": PROTOCOL,
        "version": VERSION,
        "type": frame_type,
        "sequence": sequence,
        "offset": offset,
        "payload_length": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if total_length is not None:
        header["total_length"] = total_length
    if context is not None:
        header["transfer_context"] = context
    if extra:
        for key, value in extra.items():
            if key in header:
                raise InvalidFrameError(f"reserved frame header key {key!r}")
            header[key] = value
    _validate_header(header, payload, limits)
    try:
        header_bytes = json.dumps(
            header,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvalidFrameError("frame header must contain only I-JSON values") from exc
    if len(header_bytes) > limits.max_header_bytes:
        raise FrameTooLargeError("header exceeds configured cap")
    frame_bytes = _HEADER_PREFIX.pack(len(header_bytes)) + header_bytes + payload
    if len(frame_bytes) > limits.max_frame_bytes:
        raise FrameTooLargeError("frame exceeds configured cap")
    return frame_bytes


def decode_frame(data: bytes, *, limits: FrameLimits = DEFAULT_LIMITS) -> Frame:
    if len(data) < _HEADER_PREFIX.size:
        raise InvalidFrameError("frame is missing header length")
    (header_length,) = _HEADER_PREFIX.unpack(data[: _HEADER_PREFIX.size])
    if header_length <= 0:
        raise InvalidFrameError("header length must be positive")
    if header_length > limits.max_header_bytes:
        raise FrameTooLargeError("header exceeds configured cap")
    header_start = _HEADER_PREFIX.size
    header_end = header_start + header_length
    if len(data) < header_end:
        raise InvalidFrameError("frame is truncated before header end")
    header = _loads_no_duplicate_keys(data[header_start:header_end])
    payload = data[header_end:]
    if len(data) > limits.max_frame_bytes:
        raise FrameTooLargeError("frame exceeds configured cap")
    _validate_header(header, payload, limits)
    return Frame(header=header, payload=payload)


def recv_exact(sock: socket.socket, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = byte_count
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise InvalidFrameError("socket closed during frame read")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket, *, limits: FrameLimits = DEFAULT_LIMITS) -> Frame:
    prefix = recv_exact(sock, _HEADER_PREFIX.size)
    (header_length,) = _HEADER_PREFIX.unpack(prefix)
    if header_length <= 0:
        raise InvalidFrameError("header length must be positive")
    if header_length > limits.max_header_bytes:
        raise FrameTooLargeError("header exceeds configured cap")
    header_bytes = recv_exact(sock, header_length)
    header = _loads_no_duplicate_keys(header_bytes)
    payload_length = header.get("payload_length")
    if not isinstance(payload_length, int) or isinstance(payload_length, bool) or payload_length < 0:
        raise InvalidFrameError("payload_length must be a non-negative integer")
    if payload_length > limits.max_payload_bytes:
        raise FrameTooLargeError("payload exceeds configured cap")
    payload = recv_exact(sock, payload_length)
    if _HEADER_PREFIX.size + header_length + payload_length > limits.max_frame_bytes:
        raise FrameTooLargeError("frame exceeds configured cap")
    _validate_header(header, payload, limits)
    return Frame(header=header, payload=payload)


def send_frame(sock: socket.socket, frame: bytes) -> None:
    sock.sendall(frame)
