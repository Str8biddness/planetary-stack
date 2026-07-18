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
from .profiles import (
    TEXT_CLASSIFICATION_ENTRYPOINT_ID,
    TEXT_CLASSIFICATION_RESULT_SCHEMA,
    text_classification_entrypoint,
)

__all__ = [
    "TEXT_CLASSIFICATION_ENTRYPOINT_ID",
    "TEXT_CLASSIFICATION_RESULT_SCHEMA",
    "text_classification_entrypoint",
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
