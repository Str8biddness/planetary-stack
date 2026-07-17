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
    TransferContext,
    validate_task_descriptor_bytes,
)

from .conftest import LEASE_SHA, REQUEST_SHA, StrictValidator, make_context, replace_context


def _descriptor_ref(payload: bytes) -> TaskDescriptorRef:
    return TaskDescriptorRef(descriptor_sha256=hashlib.sha256(payload).hexdigest(), byte_length=len(payload))


def test_local_process_transfer_moves_verified_bytes_and_reports_progress(tmp_path, payload: bytes) -> None:
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
    assert result.verified_receipt_sha256 == context.receipt_sha256(digest)


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


def test_task_descriptor_accepts_only_strict_v1_schema(tmp_path, payload: bytes) -> None:
    descriptor = {
        "schema": "planetary.unisync.task_descriptor.v1",
        "task_id": "task:valid",
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "byte_length": len(payload),
    }
    descriptor_payload = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    validate_task_descriptor_bytes(descriptor_payload, expected=_descriptor_ref(descriptor_payload))

    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(descriptor_payload)
    context = make_context(descriptor_payload)
    result = InProcessObjectTransport(validator=StrictValidator(), chunk_size=64).upload_task_descriptor(
        context=context,
        descriptor=TaskDescriptorRef(descriptor_sha256=digest, byte_length=len(descriptor_payload)),
        source_root=source.root,
        destination_root=tmp_path / "destination",
    )
    assert result.object_sha256 == digest


@pytest.mark.parametrize(
    ("descriptor_payload", "message"),
    [
        (
            b'{"schema":"planetary.unisync.task_descriptor.v1","schema":"planetary.unisync.task_descriptor.v1"}',
            "duplicate",
        ),
        (
            b'{"schema":"planetary.unisync.task_descriptor.v1","task_id":"task:nan","artifact_sha256":"'
            + (b"a" * 64)
            + b'","byte_length":NaN}',
            "non-I-JSON",
        ),
        (b'["not","an","object"]', "JSON object"),
        (
            b'{"schema":"planetary.unisync.task_descriptor.v1","task_id":"task:shell","artifact_sha256":"'
            + (b"a" * 64)
            + b'","byte_length":1,"command":"rm -rf /"}',
            "command",
        ),
    ],
)
def test_task_descriptor_rejects_duplicate_nan_scalar_and_command_fields(
    descriptor_payload: bytes,
    message: str,
) -> None:
    with pytest.raises(InvalidTransferContextError, match=message):
        validate_task_descriptor_bytes(descriptor_payload, expected=_descriptor_ref(descriptor_payload))


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


class RotatingLeaseValidator(StrictValidator):
    def __init__(self, *, fail_on_call: int) -> None:
        super().__init__()
        self.fail_on_call = fail_on_call

    def validate_transfer(self, context: TransferContext, peer_identity=None) -> None:
        if len(self.calls) + 1 >= self.fail_on_call:
            self.lease_sha256 = "3" * 64
        super().validate_transfer(context, peer_identity)


def test_revoked_or_renewed_lease_during_transfer_prevents_publication(tmp_path, payload: bytes) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    destination_root = tmp_path / "destination"
    validator = RotatingLeaseValidator(fail_on_call=3)

    with pytest.raises(AuthorizationError, match="wrong lease"):
        InProcessObjectTransport(validator=validator, chunk_size=64).upload_object(
            context=make_context(payload),
            source_root=source.root,
            destination_root=destination_root,
        )

    assert not ContentAddressedStore(destination_root).has(digest)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fencing_token", True, "integer"),
        ("byte_length", "5", "integer"),
        ("selected_transport", "in_process", "selected_transport"),
    ],
)
def test_transfer_context_wire_parsing_rejects_coercion_and_wrong_enum(
    payload: bytes,
    field: str,
    value,
    message: str,
) -> None:
    wire = make_context(payload).to_wire()
    wire[field] = value
    with pytest.raises(InvalidTransferContextError, match=message):
        TransferContext.from_wire(wire)


def test_transfer_context_wire_parsing_rejects_scalar_payload() -> None:
    with pytest.raises(InvalidTransferContextError, match="JSON object"):
        TransferContext.from_wire(["not", "an", "object"])
