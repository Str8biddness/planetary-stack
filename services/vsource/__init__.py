"""Durable local-only vSource control-plane service."""

from .control_plane import (
    AdmissionResult,
    AllocationResult,
    Clock,
    Ed25519DocumentSigner,
    KeyRecord,
    KeyResolver,
    LeaseResult,
    LocalVSourceControlPlane,
    VSourceStatus,
    sign_contract_document,
)

__all__ = [
    "AdmissionResult",
    "AllocationResult",
    "Clock",
    "Ed25519DocumentSigner",
    "KeyRecord",
    "KeyResolver",
    "LeaseResult",
    "LocalVSourceControlPlane",
    "VSourceStatus",
    "sign_contract_document",
]
