from __future__ import annotations

import hashlib
import os
from datetime import timedelta

import pytest

import services.unisync.storage as storage_module
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


def test_chunk_frames_must_not_be_empty() -> None:
    with pytest.raises(InvalidFrameError, match="nonempty"):
        encode_frame(FRAME_CHUNK, payload=b"")


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


def test_store_temp_symlink_and_leaf_swap_are_rejected(tmp_path, payload: bytes, monkeypatch) -> None:
    store = ContentAddressedStore(tmp_path / "cas")
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(storage_module.secrets, "token_hex", lambda size: "fixed")
    temp_path = store.root / ".tmp" / f"{digest}.fixed.tmp"
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    os.symlink(outside, temp_path)
    with pytest.raises(StorageSecurityError, match="escapes|temporary|symlink"):
        store.put_bytes(payload)

    leaf = store.object_path(digest)
    leaf.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, leaf)
    with pytest.raises(StorageSecurityError, match="symlink"):
        store.read_bytes(digest)


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


def test_pending_chunks_reject_empty_overlap_and_entry_count(tmp_path, payload: bytes) -> None:
    store = ContentAddressedStore(tmp_path / "destination")
    context = make_context(payload)
    assembler = store.start_receive(context, limits=FrameLimits(max_payload_bytes=32, max_pending_bytes=256))
    with pytest.raises(InvalidFrameError, match="nonempty"):
        assembler.receive_chunk(offset=32, payload=b"", chunk_sha256=hashlib.sha256(b"").hexdigest())

    first = payload[32:48]
    overlap = payload[40:56]
    assembler.receive_chunk(offset=32, payload=first, chunk_sha256=hashlib.sha256(first).hexdigest())
    with pytest.raises(InvalidFrameError, match="overlaps"):
        assembler.receive_chunk(offset=40, payload=overlap, chunk_sha256=hashlib.sha256(overlap).hexdigest())

    limited = ContentAddressedStore(tmp_path / "entry-limit").start_receive(
        context,
        limits=FrameLimits(max_payload_bytes=32, max_pending_bytes=256, max_pending_chunks=1),
    )
    chunk_a = payload[32:48]
    chunk_b = payload[64:80]
    limited.receive_chunk(offset=32, payload=chunk_a, chunk_sha256=hashlib.sha256(chunk_a).hexdigest())
    with pytest.raises(BackpressureError, match="entry"):
        limited.receive_chunk(offset=64, payload=chunk_b, chunk_sha256=hashlib.sha256(chunk_b).hexdigest())


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


def test_publication_fsyncs_object_and_parent_directories(tmp_path, payload: bytes, monkeypatch) -> None:
    directory_fsyncs: list[os.PathLike] = []
    monkeypatch.setattr(storage_module, "_fsync_directory", lambda path: directory_fsyncs.append(path))

    store = ContentAddressedStore(tmp_path / "cas")
    digest = store.put_bytes(payload)
    assert store.object_path(digest).parent in directory_fsyncs
    assert store.root / ".tmp" in directory_fsyncs

    directory_fsyncs.clear()
    destination = ContentAddressedStore(tmp_path / "destination")
    context = make_context(payload)
    assembler = destination.start_receive(context)
    assembler.receive_chunk(offset=0, payload=payload, chunk_sha256=hashlib.sha256(payload).hexdigest())
    directory_fsyncs.clear()
    assert assembler.finalize() == digest
    assert destination.object_path(digest).parent in directory_fsyncs
    assert destination.root / ".partials" in directory_fsyncs


def test_expired_context_is_representable(payload: bytes) -> None:
    context = make_context(payload, expires_delta=timedelta(seconds=-1))
    assert context.is_expired()


def replace_context_for_digest(context, payload: bytes):
    from .conftest import replace_context

    return replace_context(context, object_sha256=hashlib.sha256(payload + b"wrong").hexdigest(), byte_length=len(payload))
