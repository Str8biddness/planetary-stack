from __future__ import annotations

import hashlib
import os
from datetime import timedelta

import pytest

from services.unisync import (
    BackpressureError,
    ContentAddressedStore,
    DigestMismatchError,
    FRAME_CHUNK,
    FrameLimits,
    FrameTooLargeError,
    InvalidFrameError,
    StorageSecurityError,
    decode_frame,
    encode_frame,
)

from .conftest import make_context


def test_frame_bounds_reject_large_headers_payloads_and_totals(payload: bytes) -> None:
    small = FrameLimits(max_header_bytes=128, max_payload_bytes=8, max_frame_bytes=256, max_total_bytes=16)
    with pytest.raises(FrameTooLargeError, match="payload"):
        encode_frame(FRAME_CHUNK, payload=b"x" * 9, limits=small)
    with pytest.raises(FrameTooLargeError, match="total_length"):
        encode_frame(FRAME_CHUNK, payload=b"x", total_length=17, limits=small)
    with pytest.raises(FrameTooLargeError, match="header"):
        encode_frame(FRAME_CHUNK, payload=b"x", extra={"long": "x" * 500}, limits=small)


def test_frame_corruption_and_digest_mismatch_are_explicit() -> None:
    encoded = encode_frame(FRAME_CHUNK, payload=b"abc", sequence=1, offset=0)
    with pytest.raises(InvalidFrameError, match="truncated"):
        decode_frame(encoded[:5])
    corrupted = bytearray(encoded)
    corrupted[-1] ^= 0x01
    with pytest.raises(DigestMismatchError, match="payload"):
        decode_frame(bytes(corrupted))


def test_store_rejects_traversal_and_symlink_attempts(tmp_path) -> None:
    store = ContentAddressedStore(tmp_path / "cas")
    with pytest.raises(StorageSecurityError, match="digest"):
        store.object_path("../escape")

    digest = "a" * 64
    object_path = store.object_path(digest)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.write_text("secret", encoding="utf-8")
    os.symlink(outside, object_path)
    with pytest.raises(StorageSecurityError, match="symlink"):
        store.has(digest)


def test_duplicate_reorder_and_resume_offsets_finalize(tmp_path, payload: bytes) -> None:
    store = ContentAddressedStore(tmp_path / "destination")
    context = make_context(payload)
    limits = FrameLimits(max_payload_bytes=64, max_pending_bytes=256)
    assembler = store.start_receive(context, limits=limits)
    first = payload[:64]
    second = payload[64:128]
    rest = payload[128:]

    assert assembler.receive_chunk(
        offset=len(first),
        payload=second,
        chunk_sha256=hashlib.sha256(second).hexdigest(),
    ) is False
    assert assembler.receive_chunk(
        offset=len(first),
        payload=second,
        chunk_sha256=hashlib.sha256(second).hexdigest(),
    ) is False
    assert assembler.receive_chunk(offset=0, payload=first, chunk_sha256=hashlib.sha256(first).hexdigest()) is True
    assert assembler.offset == 128
    assert assembler.receive_chunk(offset=0, payload=first, chunk_sha256=hashlib.sha256(first).hexdigest()) is False
    assert assembler.receive_chunk(
        offset=128,
        payload=rest,
        chunk_sha256=hashlib.sha256(rest).hexdigest(),
    ) is True
    assert assembler.finalize() == context.object_sha256
    assert store.read_bytes(context.object_sha256) == payload

    resume_store = ContentAddressedStore(tmp_path / "resume")
    resumed = resume_store.start_receive(context, limits=limits)
    resumed.receive_chunk(offset=0, payload=first, chunk_sha256=hashlib.sha256(first).hexdigest())
    resumed_again = resume_store.start_receive(context, limits=limits)
    assert resumed_again.offset == len(first)
    resumed_again.receive_chunk(offset=len(first), payload=second, chunk_sha256=hashlib.sha256(second).hexdigest())
    resumed_again.receive_chunk(offset=128, payload=rest, chunk_sha256=hashlib.sha256(rest).hexdigest())
    assert resumed_again.finalize() == context.object_sha256


def test_reorder_buffer_is_bounded(tmp_path, payload: bytes) -> None:
    store = ContentAddressedStore(tmp_path / "destination")
    context = make_context(payload)
    assembler = store.start_receive(context, limits=FrameLimits(max_payload_bytes=128, max_pending_bytes=16))
    chunk = payload[32:96]
    with pytest.raises(BackpressureError, match="pending"):
        assembler.receive_chunk(offset=32, payload=chunk, chunk_sha256=hashlib.sha256(chunk).hexdigest())


def test_failed_final_verification_cleans_partial_data(tmp_path, payload: bytes) -> None:
    bad_payload_context = make_context(b"different" + payload)
    context = replace_context_for_digest(bad_payload_context, payload)
    store = ContentAddressedStore(tmp_path / "destination")
    assembler = store.start_receive(context)
    assembler.receive_chunk(offset=0, payload=payload, chunk_sha256=hashlib.sha256(payload).hexdigest())
    part_path, meta_path = store.partial_paths_for(context)

    with pytest.raises(DigestMismatchError, match="final object"):
        assembler.finalize()
    assert not part_path.exists()
    assert not meta_path.exists()


def test_expired_context_is_representable(payload: bytes) -> None:
    context = make_context(payload, expires_delta=timedelta(seconds=-1))
    assert context.is_expired()


def replace_context_for_digest(context, payload: bytes):
    from .conftest import replace_context

    return replace_context(context, object_sha256=hashlib.sha256(payload + b"wrong").hexdigest(), byte_length=len(payload))
