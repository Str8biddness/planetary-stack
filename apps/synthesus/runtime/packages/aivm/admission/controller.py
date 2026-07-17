"""AIVM signed-manifest admission wired to the existing execution guard."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from contracts.aivm.v1 import AIVMWorkloadManifest, signing_bytes

from ..isolation.guard import AIVMExecutionGuard


class AdmissionStatus(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DocumentVerification:
    ok: bool
    status: str
    key_id: str = ""
    error: str = ""


class DocumentVerifier(Protocol):
    """Production verifier interface expected from the trust authority worker."""

    def verify_manifest(
        self,
        manifest: AIVMWorkloadManifest,
        payload: bytes,
    ) -> DocumentVerification:
        """Verify canonical manifest bytes against enrollment/revocation policy."""


@dataclass(frozen=True)
class HostIsolationCapabilities:
    os_enforced_backend: bool
    cgroup_control: bool
    namespaces: bool
    no_new_privileges: bool
    container_runtime: bool
    guard_available: bool
    gpu_isolation: bool = False

    def missing_for(self, manifest: AIVMWorkloadManifest) -> list[str]:
        missing: list[str] = []
        if not self.os_enforced_backend:
            missing.append("os_enforced_backend")
        if not self.cgroup_control:
            missing.append("cgroup_control")
        if not self.namespaces:
            missing.append("namespaces")
        if not self.no_new_privileges:
            missing.append("no_new_privileges")
        if not self.container_runtime:
            missing.append("container_runtime")
        if not self.guard_available:
            missing.append("guard_available")
        if manifest.resources.gpu_count and not self.gpu_isolation:
            missing.append("gpu_isolation")
        return missing


@dataclass(frozen=True)
class AdmissionPolicy:
    allowed_runtime_images: frozenset[str]
    allowed_entrypoints: frozenset[str]
    max_cpu_millicores: int
    max_memory_bytes: int
    max_time_limit_seconds: int
    max_process_limit: int
    max_output_bytes: int
    allow_network: bool = False

    @staticmethod
    def image_identity(manifest: AIVMWorkloadManifest) -> str:
        return f"{manifest.runtime_image.image_id}@{manifest.runtime_image.digest}"


@dataclass(frozen=True)
class AdmissionDecision:
    status: AdmissionStatus
    reason: str
    manifest_id: str = ""
    workload_id: str = ""
    account_id: str = ""
    degraded: bool = False
    evidence: Mapping[str, object] = field(default_factory=dict)

    @property
    def admitted(self) -> bool:
        return self.status == AdmissionStatus.ADMITTED


class AIVMAdmissionController:
    """Validate signed AIVM manifests before any workload can reach execution."""

    def __init__(
        self,
        *,
        verifier: DocumentVerifier | None,
        policy: AdmissionPolicy,
        host: HostIsolationCapabilities,
        guard: AIVMExecutionGuard | None = None,
    ) -> None:
        self._verifier = verifier
        self._policy = policy
        self._host = host
        self._guard = guard or AIVMExecutionGuard()

    async def admit(
        self,
        manifest: AIVMWorkloadManifest,
        *,
        artifacts: Mapping[str, bytes],
        now: datetime | None = None,
    ) -> AdmissionDecision:
        now = now or datetime.now(timezone.utc).replace(microsecond=0)
        identity = {
            "manifest_id": manifest.manifest_id,
            "workload_id": manifest.workload_id,
            "account_id": manifest.account_id,
        }

        if self._verifier is None:
            return AdmissionDecision(
                AdmissionStatus.UNAVAILABLE,
                "document verifier unavailable",
                degraded=True,
                evidence={"missing": ["document_verifier"]},
                **identity,
            )

        host_missing = self._host.missing_for(manifest)
        if host_missing:
            return AdmissionDecision(
                AdmissionStatus.UNAVAILABLE,
                "host cannot prove required isolation",
                degraded=True,
                evidence={"missing": host_missing},
                **identity,
            )

        verification = self._verifier.verify_manifest(manifest, signing_bytes(manifest))
        if not verification.ok:
            return AdmissionDecision(
                AdmissionStatus.REJECTED,
                "manifest signature verification failed",
                evidence={"verifier_status": verification.status, "error": verification.error},
                **identity,
            )

        if now < manifest.issued_at:
            return AdmissionDecision(AdmissionStatus.REJECTED, "manifest not yet valid", **identity)
        if now >= manifest.expires_at:
            return AdmissionDecision(AdmissionStatus.REJECTED, "manifest expired", **identity)

        policy_error = self._validate_policy(manifest)
        if policy_error:
            return AdmissionDecision(AdmissionStatus.REJECTED, policy_error, **identity)

        artifact_error = self._validate_artifacts(manifest, artifacts)
        if artifact_error:
            return AdmissionDecision(AdmissionStatus.REJECTED, artifact_error, **identity)

        guard_result = await self._guard.run(
            "chal://aivm/admission",
            lambda: {
                "manifest_id": manifest.manifest_id,
                "entrypoint_id": manifest.entrypoint_id,
            },
            timeout_ms=min(manifest.resources.time_limit_seconds * 1000, 1000),
            metadata={"workload_id": manifest.workload_id},
        )
        if not guard_result.ok:
            return AdmissionDecision(
                AdmissionStatus.UNAVAILABLE,
                "AIVM execution guard unavailable",
                degraded=True,
                evidence=guard_result.to_dict(),
                **identity,
            )

        return AdmissionDecision(
            AdmissionStatus.ADMITTED,
            "manifest admitted",
            evidence={
                "artifact_count": len(manifest.artifacts),
                "runtime_image": AdmissionPolicy.image_identity(manifest),
                "entrypoint_id": manifest.entrypoint_id,
                "guard_status": guard_result.status,
                "network_mode": manifest.network.mode,
            },
            **identity,
        )

    def admit_sync(
        self,
        manifest: AIVMWorkloadManifest,
        *,
        artifacts: Mapping[str, bytes],
        now: datetime | None = None,
    ) -> AdmissionDecision:
        return asyncio.run(self.admit(manifest, artifacts=artifacts, now=now))

    def _validate_policy(self, manifest: AIVMWorkloadManifest) -> str:
        image_identity = AdmissionPolicy.image_identity(manifest)
        if image_identity not in self._policy.allowed_runtime_images:
            return "runtime image is not allowlisted"
        if manifest.entrypoint_id not in self._policy.allowed_entrypoints:
            return "entrypoint_id is not allowlisted"
        if manifest.network.mode != "deny" and not self._policy.allow_network:
            return "network is denied by admission policy"
        resources = manifest.resources
        if resources.cpu_millicores > self._policy.max_cpu_millicores:
            return "cpu budget exceeds host policy"
        if resources.memory_bytes > self._policy.max_memory_bytes:
            return "memory budget exceeds host policy"
        if resources.time_limit_seconds > self._policy.max_time_limit_seconds:
            return "time budget exceeds host policy"
        if resources.process_limit > self._policy.max_process_limit:
            return "process budget exceeds host policy"
        if resources.output_bytes > self._policy.max_output_bytes:
            return "output budget exceeds host policy"
        return ""

    @staticmethod
    def _validate_artifacts(
        manifest: AIVMWorkloadManifest,
        artifacts: Mapping[str, bytes],
    ) -> str:
        for descriptor in manifest.artifacts:
            payload = artifacts.get(descriptor.uri)
            if payload is None:
                return f"artifact unavailable: {descriptor.artifact_id}"
            if len(payload) != descriptor.size_bytes:
                return f"artifact size mismatch: {descriptor.artifact_id}"
            digest = hashlib.sha256(payload).hexdigest()
            if digest != descriptor.sha256:
                return f"artifact hash mismatch: {descriptor.artifact_id}"
        return ""
