"""Bridge admitted CHAL leases and requests into the AIVM execution boundary.

This module is the production node-agent execution wiring for F-020: the
workload bundle delivered over the mesh must be the exact canonical signed
AIVM workload manifest, and completion means real admission, durable
authority consumption, rootless Podman execution, and content-addressed
outputs with execution evidence — never an in-process shortcut.

It is imported only at composition time (node service or coordinator) with
the monorepo on the import path, because it returns the node agent's strict
:class:`WorkloadExecutionOutcome` type.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contracts.aivm.v1 import AIVMWorkloadManifest
from contracts.aivm.v1 import document_sha256 as aivm_document_sha256
from contracts.chal_vsource.v1.canonical import document_sha256 as chal_document_sha256
from contracts.chal_vsource.v1.models import ChalRequest, LeaseDocument, LeaseState
from services.private_mesh.node_agent import WorkloadExecutionOutcome

from ..admission import AIVMAdmissionController
from .authority import AuthorityRegistrationError, PersistentExecutionAuthority
from .podman import (
    AdmittedExecutionRequest,
    ExecutionStatus,
    InvalidExecutionRequest,
    LeaseAuthority,
    PodmanExecutor,
)

AIVM_EVIDENCE_MEDIA_TYPE = "application/vnd.planetary.aivm-evidence+json"
_READ_CHUNK = 65_536


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key is not allowed: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric value is not allowed: {value}")


def _failure(reason: str, *, unavailable: bool = False) -> WorkloadExecutionOutcome:
    return WorkloadExecutionOutcome(ok=False, reason=reason, unavailable=unavailable)


class ChalWorkloadExecutor:
    """Execute one admitted CHAL workload through the real AIVM boundary."""

    def __init__(
        self,
        *,
        executor: PodmanExecutor,
        authority: PersistentExecutionAuthority,
        admission: AIVMAdmissionController,
        artifact_dir: Path,
        max_artifact_bytes: int = 256 * 1024 * 1024,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if executor is None or authority is None or admission is None:
            raise ValueError("executor, authority, and admission are all required")
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")
        self._executor = executor
        self._authority = authority
        self._admission = admission
        self._artifact_dir = Path(artifact_dir)
        self._max_artifact_bytes = max_artifact_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime | None:
        try:
            now = self._clock()
        except Exception:
            return None
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            return None
        return now.astimezone(UTC).replace(microsecond=0)

    def _load_artifact(self, sha256: str, size_bytes: int) -> bytes | None:
        if size_bytes > self._max_artifact_bytes:
            return None
        path = self._artifact_dir / sha256
        try:
            info = path.lstat()
        except OSError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_size != size_bytes:
            return None
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return None
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        measured = 0
        try:
            while True:
                chunk = os.read(fd, _READ_CHUNK)
                if not chunk:
                    break
                measured += len(chunk)
                if measured > size_bytes:
                    return None
                digest.update(chunk)
                chunks.append(chunk)
        except OSError:
            return None
        finally:
            os.close(fd)
        if measured != size_bytes or digest.hexdigest() != sha256:
            return None
        return b"".join(chunks)

    def execute_workload(
        self,
        *,
        lease: LeaseDocument,
        request: ChalRequest,
        bundle: bytes,
    ) -> WorkloadExecutionOutcome:
        if type(lease) is not LeaseDocument or type(request) is not ChalRequest:
            return _failure("execution_context_invalid")
        if not isinstance(bundle, (bytes, bytearray, memoryview)):
            return _failure("bundle_not_bytes")
        if lease.state is not LeaseState.ACTIVE:
            return _failure("lease_not_active")
        now = self._now()
        if now is None:
            return _failure("clock_unavailable", unavailable=True)
        raw = bytes(bundle)
        try:
            # I-JSON strictness (duplicate keys, non-finite numbers) first,
            # then JSON-mode model validation so canonical wire enums load.
            json.loads(
                raw,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
            manifest = AIVMWorkloadManifest.model_validate_json(raw)
        except (TypeError, ValueError):
            return _failure("bundle_not_a_workload_manifest")
        if not isinstance(manifest, AIVMWorkloadManifest):
            return _failure("bundle_not_a_workload_manifest")
        if manifest.account_id != lease.account_id:
            return _failure("manifest_account_mismatch")

        artifacts: dict[str, bytes] = {}
        for descriptor in manifest.artifacts:
            data = self._load_artifact(descriptor.sha256, descriptor.size_bytes)
            if data is None:
                return _failure("input_artifact_unavailable")
            artifacts[descriptor.uri] = data

        try:
            decision = self._admission.admit_sync(manifest, artifacts=artifacts, now=now)
        except Exception:
            return _failure("admission_unavailable", unavailable=True)
        if not decision.admitted:
            if decision.degraded:
                return _failure("admission_unavailable", unavailable=True)
            return _failure("manifest_not_admitted")

        lease_sha256 = chal_document_sha256(lease)
        expires_at = lease.not_before + timedelta(seconds=lease.ttl_seconds)
        try:
            self._authority.register(
                account_id=lease.account_id,
                node_id=lease.node_id,
                lease_id=lease.lease_id,
                lease_sha256=lease_sha256,
                fencing_token=lease.fencing_token,
                manifest_sha256=aivm_document_sha256(manifest),
                workload_id=manifest.workload_id,
                expires_at=expires_at,
                now=now,
            )
        except AuthorityRegistrationError as exc:
            return _failure(str(exc))
        except Exception:
            return _failure("authority_unavailable", unavailable=True)

        try:
            lease_authority = LeaseAuthority(
                account_id=lease.account_id,
                workload_id=manifest.workload_id,
                node_id=lease.node_id,
                lease_id=lease.lease_id,
                lease_sha256=lease_sha256,
                fencing_token=lease.fencing_token,
            )
            admitted = AdmittedExecutionRequest(manifest, decision, lease_authority)
        except InvalidExecutionRequest as exc:
            return _failure(str(exc))

        result = self._executor.execute(admitted)
        if result.status is ExecutionStatus.UNAVAILABLE:
            return _failure(result.reason, unavailable=True)
        if result.status is not ExecutionStatus.SUCCEEDED or result.evidence is None:
            return _failure(result.reason)

        evidence_bytes = json.dumps(
            result.evidence.to_record(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
        outputs: list[dict[str, object]] = []
        for output in result.evidence.outputs:
            if output.get("transport") == "bounded_stdout_json":
                outputs.append(
                    {
                        "uri": str(output["uri"]),
                        "sha256": str(output["sha256"]),
                        "size_bytes": int(output["size_bytes"]),
                        "media_type": str(output["media_type"]),
                        "classification": "private",
                    }
                )
        outputs.append(
            {
                "uri": f"artifact://aivm/evidence/{evidence_sha256}",
                "sha256": evidence_sha256,
                "size_bytes": len(evidence_bytes),
                "media_type": AIVM_EVIDENCE_MEDIA_TYPE,
                "classification": "private",
            }
        )
        return WorkloadExecutionOutcome(
            ok=True,
            outputs=tuple(outputs),
            report=evidence_bytes,
        )
