"""Explicit Unisync error taxonomy."""

from __future__ import annotations


class UnisyncError(Exception):
    """Base class for all Unisync transport failures."""


class AuthorizationError(UnisyncError):
    """The injected CHAL/vSource authorization or active lease rejected a transfer."""


class InvalidTransferContextError(UnisyncError):
    """A transfer context is malformed or does not bind the requested transfer."""


class ExpiredContextError(InvalidTransferContextError):
    """The transfer context expired before the transport began or completed."""


class TotalSizeExceededError(InvalidTransferContextError):
    """The declared object total exceeds the configured transport cap."""


class InvalidFrameError(UnisyncError):
    """A frame is malformed, unsupported, corrupt, duplicated incorrectly, or reordered unsafely."""


class FrameTooLargeError(InvalidFrameError):
    """A frame header, payload, or whole frame exceeds configured bounds."""


class DigestMismatchError(UnisyncError):
    """A chunk or finalized object digest does not match its signed descriptor."""


class StorageSecurityError(UnisyncError):
    """Object storage confinement, traversal, symlink, or permission checks failed."""


class CancellationError(UnisyncError):
    """The caller cancelled an active transfer."""


class DeadlineExceededError(UnisyncError):
    """The transfer exceeded its caller-provided deadline."""


class BackpressureError(UnisyncError):
    """The receiver or caller refused more in-flight bytes."""


class TLSConfigurationError(UnisyncError):
    """The trusted-LAN TLS backend was configured insecurely."""
