"""Rootless, fail-closed AIVM execution backends."""

from .podman import (
    AdmittedExecutionRequest,
    AuthorityStatus,
    AuthorityVerification,
    CommandResult,
    ExecutionAuthorityVerifier,
    ExecutionEvidence,
    ExecutionResult,
    ExecutionStatus,
    ExecutorPolicy,
    HostCapabilityEvidence,
    LeaseAuthority,
    PodmanExecutor,
    ReplayRejected,
    ReplayStore,
    SubprocessCommandRunner,
    TrustedEntrypoint,
)

__all__ = [
    "AdmittedExecutionRequest",
    "AuthorityStatus",
    "AuthorityVerification",
    "CommandResult",
    "ExecutionAuthorityVerifier",
    "ExecutionEvidence",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutorPolicy",
    "HostCapabilityEvidence",
    "LeaseAuthority",
    "PodmanExecutor",
    "ReplayRejected",
    "ReplayStore",
    "SubprocessCommandRunner",
    "TrustedEntrypoint",
]
