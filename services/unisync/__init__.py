"""Canonical bounded Unisync transport primitives.

Unisync is a data transport below CHAL/vSource admission.  This package does
not select nodes, grant authority, enroll devices, discover peers, or schedule
workloads; callers must inject the active authorization and fenced-lease
validator from the control plane before any bytes move.
"""

from .contracts import (
    AuthenticatedPeerIdentity,
    AuthorizationLeaseValidator,
    BackpressureController,
    CancellationToken,
    Deadline,
    ObjectTransport,
    TaskDescriptorRef,
    TaskDescriptorTransport,
    TransferContext,
    TransferProgress,
    TransferResult,
    validate_task_descriptor_bytes,
)
from .deferred import DeferredTransport
from .errors import (
    AuthorizationError,
    BackpressureError,
    CancellationError,
    DeadlineExceededError,
    DigestMismatchError,
    ExpiredContextError,
    FrameTooLargeError,
    InvalidFrameError,
    InvalidTransferContextError,
    StorageSecurityError,
    TLSConfigurationError,
    TotalSizeExceededError,
    UnisyncError,
)
from .framing import (
    DEFAULT_LIMITS,
    FRAME_COMPLETE,
    FRAME_ERROR,
    FRAME_START,
    FRAME_ACK,
    FRAME_CANCEL,
    FRAME_CHUNK,
    PROTOCOL,
    VERSION,
    Frame,
    FrameLimits,
    decode_frame,
    encode_frame,
)
from .local import InProcessObjectTransport
from .storage import ContentAddressedStore, ObjectAssembler
from .tls import EnrolledPeerIdentity, TrustedLanClient, TrustedLanServer, TLSCredentials

__all__ = [
    "AuthorizationError",
    "AuthorizationLeaseValidator",
    "AuthenticatedPeerIdentity",
    "BackpressureController",
    "BackpressureError",
    "CancellationError",
    "CancellationToken",
    "ContentAddressedStore",
    "DEFAULT_LIMITS",
    "Deadline",
    "DeadlineExceededError",
    "DeferredTransport",
    "DigestMismatchError",
    "ExpiredContextError",
    "EnrolledPeerIdentity",
    "FRAME_ACK",
    "FRAME_CANCEL",
    "FRAME_CHUNK",
    "FRAME_COMPLETE",
    "FRAME_ERROR",
    "FRAME_START",
    "Frame",
    "FrameLimits",
    "FrameTooLargeError",
    "InProcessObjectTransport",
    "InvalidFrameError",
    "InvalidTransferContextError",
    "ObjectAssembler",
    "ObjectTransport",
    "PROTOCOL",
    "StorageSecurityError",
    "TLSConfigurationError",
    "TLSCredentials",
    "TaskDescriptorRef",
    "TaskDescriptorTransport",
    "TotalSizeExceededError",
    "TransferContext",
    "TransferProgress",
    "TransferResult",
    "TrustedLanClient",
    "TrustedLanServer",
    "UnisyncError",
    "VERSION",
    "decode_frame",
    "encode_frame",
    "validate_task_descriptor_bytes",
]
