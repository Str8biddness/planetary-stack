"""In-process Unisync object transport for integration tests and local cells."""

from __future__ import annotations

from pathlib import Path

from .contracts import (
    AuthorizationLeaseValidator,
    BackpressureController,
    CancellationToken,
    Deadline,
    ProgressCallback,
    TaskDescriptorRef,
    TransferContext,
    TransferProgress,
    TransferResult,
    require_authorized,
    validate_task_descriptor_bytes,
)
from .framing import DEFAULT_LIMITS, FRAME_CHUNK, FRAME_COMPLETE, FRAME_START, FrameLimits, decode_frame, encode_frame
from .storage import ContentAddressedStore


class InProcessObjectTransport:
    """Real local byte-copy backend with the same frame and verifier rules."""

    transport_id = "local_process"

    def __init__(
        self,
        *,
        validator: AuthorizationLeaseValidator | None,
        limits: FrameLimits = DEFAULT_LIMITS,
        chunk_size: int | None = None,
        backpressure: BackpressureController | None = None,
    ) -> None:
        self.validator = validator
        self.limits = limits
        self.chunk_size = chunk_size or limits.max_payload_bytes
        if self.chunk_size <= 0 or self.chunk_size > limits.max_payload_bytes:
            raise ValueError("chunk_size must be positive and no larger than max_payload_bytes")
        self.backpressure = backpressure

    def upload_object(
        self,
        *,
        context: TransferContext,
        source_root: Path,
        destination_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult:
        require_authorized(
            context,
            validator=self.validator,
            transport_id=self.transport_id,
            max_total_bytes=self.limits.max_total_bytes,
        )
        token = cancellation or CancellationToken()
        source = ContentAddressedStore(source_root)
        destination = ContentAddressedStore(destination_root)
        if source.stat_size(context.object_sha256) != context.byte_length:
            raise ValueError("source object size does not match transfer context")
        assembler = destination.start_receive(context, limits=self.limits)
        resumed_from = assembler.offset
        transferred = resumed_from
        try:
            start_frame = encode_frame(
                FRAME_START,
                context=context.to_wire(),
                total_length=context.byte_length,
                extra={"resume_offset": resumed_from},
                limits=self.limits,
            )
            decode_frame(start_frame, limits=self.limits)
            with source.open_read(context.object_sha256, offset=resumed_from) as handle:
                sequence = 0
                offset = resumed_from
                while offset < context.byte_length:
                    token.raise_if_cancelled()
                    if deadline is not None:
                        deadline.raise_if_expired()
                    payload = handle.read(min(self.chunk_size, context.byte_length - offset))
                    if not payload:
                        break
                    if self.backpressure is not None:
                        self.backpressure.acquire(len(payload))
                    try:
                        frame_bytes = encode_frame(
                            FRAME_CHUNK,
                            payload=payload,
                            sequence=sequence,
                            offset=offset,
                            total_length=context.byte_length,
                            context=context.to_wire(),
                            limits=self.limits,
                        )
                        frame = decode_frame(frame_bytes, limits=self.limits)
                        require_authorized(
                            context,
                            validator=self.validator,
                            transport_id=self.transport_id,
                            max_total_bytes=self.limits.max_total_bytes,
                        )
                        assembler.receive_chunk(
                            offset=int(frame.header["offset"]),
                            payload=frame.payload,
                            chunk_sha256=str(frame.header["payload_sha256"]),
                        )
                    finally:
                        if self.backpressure is not None:
                            self.backpressure.release(len(payload))
                    offset += len(payload)
                    transferred = offset
                    sequence += 1
                    if progress is not None:
                        progress(
                            TransferProgress(
                                context=context,
                                bytes_transferred=transferred,
                                total_bytes=context.byte_length,
                                chunk_index=sequence,
                                resumed_from=resumed_from,
                            )
                        )
                if offset != context.byte_length:
                    raise ValueError("source object ended before declared transfer length")
            complete_frame = encode_frame(
                FRAME_COMPLETE,
                sequence=sequence,
                offset=context.byte_length,
                total_length=context.byte_length,
                context=context.to_wire(),
                extra={"object_sha256": context.object_sha256},
                limits=self.limits,
            )
            decode_frame(complete_frame, limits=self.limits)
            require_authorized(
                context,
                validator=self.validator,
                transport_id=self.transport_id,
                max_total_bytes=self.limits.max_total_bytes,
            )
            digest = assembler.finalize()
            if progress is not None:
                progress(
                    TransferProgress(
                        context=context,
                        bytes_transferred=context.byte_length,
                        total_bytes=context.byte_length,
                        chunk_index=sequence,
                        resumed_from=resumed_from,
                        complete=True,
                    )
                )
            return TransferResult(
                context=context,
                object_sha256=digest,
                bytes_transferred=transferred - resumed_from,
                resumed_from=resumed_from,
                transport_id=self.transport_id,
                verified_receipt_sha256=context.receipt_sha256(digest),
            )
        except Exception:
            assembler.abort()
            raise

    def upload_task_descriptor(
        self,
        *,
        context: TransferContext,
        descriptor: TaskDescriptorRef,
        source_root: Path,
        destination_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult:
        source = ContentAddressedStore(source_root)
        validate_task_descriptor_bytes(source.read_bytes(descriptor.descriptor_sha256), expected=descriptor)
        if context.object_sha256 != descriptor.descriptor_sha256 or context.byte_length != descriptor.byte_length:
            raise ValueError("task descriptor reference does not match transfer context")
        return self.upload_object(
            context=context,
            source_root=source_root,
            destination_root=destination_root,
            cancellation=cancellation,
            deadline=deadline,
            progress=progress,
        )
