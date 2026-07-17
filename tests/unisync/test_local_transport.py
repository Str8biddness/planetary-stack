from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest

from services.unisync import (
    AuthorizationError,
    BackpressureController,
    BackpressureError,
    CancellationToken,
    ContentAddressedStore,
    Deadline,
    DeadlineExceededError,
    ExpiredContextError,
    FrameLimits,
    InProcessObjectTransport,
    InvalidTransferContextError,
    TaskDescriptorRef,
    TotalSizeExceededError,
)

from .conftest import LEASE_SHA, REQUEST_SHA, StrictValidator, make_context, replace_context


def test_in_process_transfer_moves_verified_bytes_and_reports_progress(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    destination_root = tmp_path / "destination"
    context = make_context(payload)
    assert context.object_sha256 == digest
    progress = []
    transport = InProcessObjectTransport(validator=StrictValidator(), chunk_size=80)

    result = transport.upload_object(
        context=context,
        source_root=source.root,
        destination_root=destination_root,
        progress=progress.append,
    )

    destination = ContentAddressedStore(destination_root)
    assert result.object_sha256 == digest
    assert result.bytes_transferred == len(payload)
    assert result.resumed_from == 0
    assert destination.read_bytes(digest) == payload
    assert progress[-1].complete is True


def test_task_descriptor_transport_rejects_raw_prompt_fields(tmp_path) -> None:
    descriptor = {"schema": "planetary.task.v1", "prompt": "raw user content must not be here"}
    payload = json.dumps(descriptor, sort_keys=True).encode("utf-8")
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    context = make_context(payload)
    ref = TaskDescriptorRef(descriptor_sha256=digest, byte_length=len(payload))
    transport = InProcessObjectTransport(validator=StrictValidator(), chunk_size=64)

    with pytest.raises(InvalidTransferContextError, match="prompt"):
        transport.upload_task_descriptor(
            context=context,
            descriptor=ref,
            source_root=source.root,
            destination_root=tmp_path / "destination",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("account_id", "account:other", "wrong account"),
        ("lease_sha256", "3" * 64, "wrong lease"),
        ("fencing_token", 99, "wrong fencing"),
    ],
)
def test_injected_validator_rejects_wrong_account_lease_and_fence(
    tmp_path,
    payload: bytes,
    field: str,
    value,
    message: str,
) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    context = replace_context(make_context(payload), **{field: value})
    transport = InProcessObjectTransport(validator=StrictValidator())

    with pytest.raises(AuthorizationError, match=message):
        transport.upload_object(context=context, source_root=source.root, destination_root=tmp_path / "destination")


def test_expired_context_rejected_before_transport(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    context = make_context(payload, expires_delta=timedelta(seconds=-1))
    validator = StrictValidator()
    transport = InProcessObjectTransport(validator=validator)

    with pytest.raises(ExpiredContextError, match="expired"):
        transport.upload_object(context=context, source_root=source.root, destination_root=tmp_path / "destination")
    assert validator.calls == []


def test_transport_cannot_bypass_injected_admission(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    destination_root = tmp_path / "destination"
    transport = InProcessObjectTransport(validator=StrictValidator(allow=False), chunk_size=64)

    with pytest.raises(AuthorizationError, match="denied"):
        transport.upload_object(
            context=make_context(payload),
            source_root=source.root,
            destination_root=destination_root,
        )
    assert not ContentAddressedStore(destination_root).has(digest)


def test_transfer_requires_an_injected_validator(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    transport = InProcessObjectTransport(validator=None)

    with pytest.raises(AuthorizationError, match="requires an injected"):
        transport.upload_object(
            context=make_context(payload),
            source_root=source.root,
            destination_root=tmp_path / "destination",
        )


def test_cancellation_timeout_backpressure_and_oversized_totals_cleanup_partials(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    destination_root = tmp_path / "destination"
    context = make_context(payload)

    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception, match="cancelled"):
        InProcessObjectTransport(validator=StrictValidator(), chunk_size=64).upload_object(
            context=context,
            source_root=source.root,
            destination_root=destination_root,
            cancellation=token,
        )
    assert not any((destination_root / ".partials").glob("*"))

    with pytest.raises(DeadlineExceededError, match="deadline"):
        InProcessObjectTransport(validator=StrictValidator(), chunk_size=64).upload_object(
            context=context,
            source_root=source.root,
            destination_root=destination_root,
            deadline=Deadline.after(-1),
        )
    assert not any((destination_root / ".partials").glob("*"))

    with pytest.raises(BackpressureError, match="chunk exceeds"):
        InProcessObjectTransport(
            validator=StrictValidator(),
            chunk_size=64,
            backpressure=BackpressureController(max_inflight_bytes=8),
        ).upload_object(context=context, source_root=source.root, destination_root=destination_root)
    assert not any((destination_root / ".partials").glob("*"))

    oversized = replace_context(context, byte_length=1024)
    with pytest.raises(TotalSizeExceededError, match="total cap"):
        InProcessObjectTransport(
            validator=StrictValidator(),
            limits=FrameLimits(max_total_bytes=128),
        ).upload_object(context=oversized, source_root=source.root, destination_root=destination_root)


def test_resume_offset_is_used_by_local_transport(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    destination = ContentAddressedStore(tmp_path / "destination")
    context = make_context(payload)
    first = payload[:96]
    assembler = destination.start_receive(context)
    assembler.receive_chunk(offset=0, payload=first, chunk_sha256=hashlib.sha256(first).hexdigest())

    result = InProcessObjectTransport(validator=StrictValidator(), chunk_size=64).upload_object(
        context=context,
        source_root=source.root,
        destination_root=destination.root,
    )

    assert result.resumed_from == len(first)
    assert destination.read_bytes(context.object_sha256) == payload
