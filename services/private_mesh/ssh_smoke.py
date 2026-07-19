"""Pinned-SSH physical smoke coordinator for two private-mesh nodes.

This is an acceptance harness, not a production transport.  OpenSSH carries a
single bounded JSON job to a fixed node-local program.  The frozen signed
contract truthfully records ``local_process`` because execution occurs inside
that remote process; this harness never claims that SSH proves Unisync mTLS.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    LeaseDocument,
    LeaseState,
    LifecycleEvent,
    LifecycleState,
    ResourceInventory,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
)
from services.private_mesh.node_agent import (
    HASH_REPORT_MEDIA_TYPE,
    HASH_REPORT_SCHEMA,
)
from services.private_mesh.worker_cli import implementation_sha256
from services.vsource import (
    Ed25519DocumentSigner,
    KeyRecord,
    LocalVSourceControlPlane,
    VSourceStatus,
    sign_contract_document,
)


ACCOUNT_DEFAULT = "account:owner:private-mesh"
SUBJECT_DEFAULT = "node-agent:private-mesh"
AIVM_EVIDENCE_MEDIA_TYPE = "application/vnd.planetary.aivm-evidence+json"
MAX_SSH_OUTPUT_BYTES = 4 * 1024 * 1024
_SAFE_ALIAS_RE = re.compile(r"^[A-Za-z0-9_.@:-]{1,255}$")
_SAFE_REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9_./:+@-]{1,1023}$")
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}=?$")
_ENROLLMENT_FIELDS = frozenset(
    {
        "schema",
        "hostname",
        "implementation_sha256",
        "architecture",
        "logical_cores",
        "account_id",
        "node_id",
        "key_id",
        "public_key_base64",
        "public_key_fingerprint",
        "inventory_sha256",
        "inventory",
    }
)
_RESULT_FIELDS = frozenset(
    {"schema", "hostname", "node_id", "admission", "execution"}
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric constant: {value}")


def _strict_json(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    result = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    if not isinstance(result, dict):
        raise ValueError("JSON document must be an object")
    json.dumps(result, allow_nan=False, separators=(",", ":"))
    return result


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: object, *, expected_bytes: int | None = None) -> bytes:
    if not isinstance(value, str) or "=" in value:
        raise ValueError("base64url value must be an unpadded string")
    try:
        result = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64url value") from exc
    if _b64url_encode(result) != value:
        raise ValueError("base64url value is not canonical")
    if expected_bytes is not None and len(result) != expected_bytes:
        raise ValueError(f"base64url value must encode {expected_bytes} bytes")
    return result


def _wire_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wire_model(model_type: Any, payload: object) -> Any:
    return model_type.model_validate_json(
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
    )


def _require_identifier(name: str, value: str) -> None:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{name} must be a canonical contract identifier")


def _signer(key_id: str) -> Ed25519DocumentSigner:
    return Ed25519DocumentSigner(key_id, Ed25519PrivateKey.generate())


def _signer_public_bytes(signer: Ed25519DocumentSigner) -> bytes:
    return signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _verify_ed25519_document(
    document: Any,
    *,
    public_key: bytes,
    expected_key_id: str,
) -> None:
    if document.signature.key_id != expected_key_id:
        raise ValueError("signed document uses an unexpected key identifier")
    signature = _b64url_decode(document.signature.value, expected_bytes=64)
    Ed25519PublicKey.from_public_bytes(public_key).verify(
        signature,
        signing_bytes(document),
    )


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class MemoryResolver:
    def __init__(self) -> None:
        self._records: dict[str, KeyRecord] = {}

    def add(self, record: KeyRecord) -> None:
        if record.key_id in self._records:
            raise ValueError(f"duplicate trust record: {record.key_id}")
        self._records[record.key_id] = record

    def resolve_key(self, key_id: str) -> KeyRecord | None:
        return self._records.get(key_id)


@dataclass(frozen=True)
class NodeTarget:
    node_id: str
    ssh_alias: str
    ssh_host_fingerprint: str
    remote_python: str
    remote_repo: str
    remote_state_dir: str

    @classmethod
    def parse(cls, value: str) -> "NodeTarget":
        parts = value.split("|")
        if len(parts) != 6:
            raise ValueError(
                "--node requires NODE_ID|SSH_ALIAS|HOST_FINGERPRINT|PYTHON|REPO|STATE_DIR"
            )
        target = cls(*parts)
        _require_identifier("node_id", target.node_id)
        if not _SAFE_ALIAS_RE.fullmatch(target.ssh_alias):
            raise ValueError("SSH alias contains unsupported characters")
        if not _HOST_FINGERPRINT_RE.fullmatch(target.ssh_host_fingerprint):
            raise ValueError("SSH host fingerprint must be SHA256 base64")
        for name, path in (
            ("remote_python", target.remote_python),
            ("remote_repo", target.remote_repo),
            ("remote_state_dir", target.remote_state_dir),
        ):
            if not _SAFE_REMOTE_PATH_RE.fullmatch(path) or ".." in Path(path).parts:
                raise ValueError(f"{name} must be a safe absolute path")
        return target


class SshCarrier:
    """Invoke the fixed worker CLI over a strict OpenSSH carrier."""

    def __init__(
        self,
        *,
        known_hosts: Path,
        identity_file: Path | None,
        timeout_seconds: int,
    ) -> None:
        self.known_hosts = known_hosts.expanduser().resolve()
        self.identity_file = (
            identity_file.expanduser().resolve() if identity_file is not None else None
        )
        self.timeout_seconds = timeout_seconds
        if not self.known_hosts.is_file():
            raise ValueError("known_hosts must name an existing regular file")
        if self.identity_file is not None and not self.identity_file.is_file():
            raise ValueError("identity file must name an existing regular file")

    def _base_argv(self, alias: str) -> list[str]:
        argv = [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "VerifyHostKeyDNS=no",
            "-o",
            "UpdateHostKeys=no",
            "-o",
            "HostKeyAlgorithms=ssh-ed25519",
            "-o",
            "KnownHostsCommand=none",
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPath=none",
            "-o",
            "ControlPersist=no",
            "-o",
            "NoHostAuthenticationForLocalhost=no",
            "-o",
            "ForwardX11=no",
            "-o",
            "ForwardX11Trusted=no",
            "-o",
            "Tunnel=no",
            "-o",
            "PermitLocalCommand=no",
            "-o",
            "ForwardAgent=no",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "ConnectTimeout=10",
        ]
        if self.identity_file is not None:
            argv.extend(["-o", "IdentitiesOnly=yes", "-i", str(self.identity_file)])
        argv.append(alias)
        return argv

    def _ssh_config(self, alias: str) -> tuple[str, int, str]:
        completed = subprocess.run(
            ["ssh", "-G", alias],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"could not resolve SSH alias {alias!r}")
        settings: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition(" ")
            if separator and key not in settings:
                settings[key] = value.strip()
        host = settings.get("hostname")
        host_key_alias = settings.get("hostkeyalias", host or "")
        port_text = settings.get("port", "22")
        if (
            not host
            or not _SAFE_ALIAS_RE.fullmatch(host)
            or not _SAFE_ALIAS_RE.fullmatch(host_key_alias)
            or not port_text.isdigit()
        ):
            raise RuntimeError(f"SSH alias {alias!r} resolved to unsafe host settings")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise RuntimeError("SSH port is outside the valid range")
        return host, port, host_key_alias

    def verify_pinned_host(self, target: NodeTarget) -> dict[str, Any]:
        host, port, host_key_alias = self._ssh_config(target.ssh_alias)
        lookup = host_key_alias if port == 22 else f"[{host_key_alias}]:{port}"
        found = subprocess.run(
            ["ssh-keygen", "-F", lookup, "-f", str(self.known_hosts)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        fingerprints: list[str] = []
        matching_lines = 0
        for line in found.stdout.splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if fields[0].startswith("@") or len(fields) != 3:
                raise RuntimeError(
                    f"host pin for {target.ssh_alias} must be one raw host key"
                )
            if fields[1] != "ssh-ed25519":
                raise RuntimeError(
                    f"host pin for {target.ssh_alias} must be an Ed25519 key"
                )
            matching_lines += 1
            rendered = subprocess.run(
                ["ssh-keygen", "-lf", "-", "-E", "sha256"],
                input=(line + "\n").encode("utf-8"),
                check=False,
                capture_output=True,
                timeout=10,
            )
            if rendered.returncode == 0:
                fields = rendered.stdout.decode("utf-8", errors="strict").split()
                if len(fields) >= 2 and fields[1].startswith("SHA256:"):
                    fingerprints.append(fields[1])
        if matching_lines != 1 or fingerprints != [target.ssh_host_fingerprint]:
            raise RuntimeError(
                f"known_hosts must contain exactly the expected host key for {target.ssh_alias}"
            )
        return {
            "ssh_alias": target.ssh_alias,
            "resolved_host": host,
            "resolved_port": port,
            "host_key_alias": host_key_alias,
            "ssh_host_fingerprint": target.ssh_host_fingerprint,
        }

    @staticmethod
    def _remote_command(target: NodeTarget, *arguments: str) -> str:
        fixed = [
            target.remote_python,
            "-m",
            "services.private_mesh.worker_cli",
            *arguments,
        ]
        return (
            f"cd {shlex.quote(target.remote_repo)} && "
            f"env PYTHONPATH=. {' '.join(shlex.quote(value) for value in fixed)}"
        )

    def _run(
        self,
        target: NodeTarget,
        command: str,
        *,
        stdin: bytes | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        returncode, stdout, _stderr = self._run_bounded_process(
            [*self._base_argv(target.ssh_alias), command],
            stdin=stdin,
            cancel_event=cancel_event,
        )
        output = _strict_json(stdout.strip()) if stdout.strip() else {}
        if returncode != 0:
            message = output.get("message", "worker command failed")
            raise RuntimeError(f"worker {target.node_id} rejected the command: {message}")
        return output

    def _run_bounded_process(
        self,
        argv: list[str],
        *,
        stdin: bytes | None,
        cancel_event: Event | None = None,
    ) -> tuple[int, bytes, bytes]:
        overflow = Event()
        overflow_stream: list[str] = []
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()

        with tempfile.TemporaryFile() as input_file:
            if stdin is not None:
                input_file.write(stdin)
                input_file.seek(0)
            process = subprocess.Popen(
                argv,
                stdin=input_file if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdout is not None
            assert process.stderr is not None

            def drain(stream: Any, output: bytearray, label: str) -> None:
                while True:
                    chunk = stream.read(65_536)
                    if not chunk:
                        return
                    if len(output) + len(chunk) > MAX_SSH_OUTPUT_BYTES:
                        overflow_stream.append(label)
                        overflow.set()
                        process.kill()
                        return
                    output.extend(chunk)

            readers = [
                Thread(
                    target=drain,
                    args=(process.stdout, stdout_buffer, "stdout"),
                    daemon=True,
                ),
                Thread(
                    target=drain,
                    args=(process.stderr, stderr_buffer, "stderr"),
                    daemon=True,
                ),
            ]
            for reader in readers:
                reader.start()
            try:
                if cancel_event is not None:
                    deadline = time.monotonic() + self.timeout_seconds
                    returncode = None
                    while time.monotonic() < deadline:
                        if cancel_event.is_set():
                            process.kill()
                            process.wait(timeout=5)
                            raise RuntimeError("worker SSH command was cancelled")
                        try:
                            returncode = process.wait(timeout=0.1)
                            break
                        except subprocess.TimeoutExpired:
                            pass
                    if returncode is None:
                        raise subprocess.TimeoutExpired(process.args, self.timeout_seconds)
                else:
                    returncode = process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError("worker SSH command exceeded its time limit") from exc
            finally:
                for reader in readers:
                    reader.join(timeout=5)
            if overflow.is_set():
                stream = overflow_stream[0] if overflow_stream else "output"
                raise RuntimeError(f"worker SSH {stream} exceeded the output bound")
        return returncode, bytes(stdout_buffer), bytes(stderr_buffer)

    def enroll(
        self,
        target: NodeTarget,
        *,
        account_id: str,
        subject_id: str,
    ) -> dict[str, Any]:
        command = self._remote_command(
            target,
            "enroll",
            "--state-dir",
            target.remote_state_dir,
            "--account-id",
            account_id,
            "--node-id",
            target.node_id,
            "--authenticated-subject-id",
            subject_id,
        )
        return self._run(target, command)

    def execute(self, target: NodeTarget, job: dict[str, Any], cancel_event: Event | None = None) -> dict[str, Any]:
        command = self._remote_command(
            target,
            "execute",
            "--state-dir",
            target.remote_state_dir,
        )
        encoded = json.dumps(
            job,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._run(target, command, stdin=encoded, cancel_event=cancel_event)


def _validate_enrollment(
    target: NodeTarget,
    payload: dict[str, Any],
    *,
    account_id: str,
) -> tuple[ResourceInventory, bytes]:
    if set(payload) != _ENROLLMENT_FIELDS:
        raise ValueError(f"worker {target.node_id} returned unexpected enrollment fields")
    if payload["schema"] != "planetary.private_mesh.enrollment.v1":
        raise ValueError("worker returned an unsupported enrollment schema")
    if payload["account_id"] != account_id or payload["node_id"] != target.node_id:
        raise ValueError("worker enrollment identity does not match the target")
    if payload["implementation_sha256"] != implementation_sha256():
        raise ValueError("remote worker implementation differs from the coordinator")
    public_key = _b64url_decode(payload["public_key_base64"], expected_bytes=32)
    fingerprint = hashlib.sha256(public_key).hexdigest()
    if fingerprint != payload["public_key_fingerprint"]:
        raise ValueError("worker public-key fingerprint is invalid")
    inventory = _wire_model(ResourceInventory, payload["inventory"])
    if (
        inventory.account_id != account_id
        or inventory.node_id != target.node_id
        or inventory.signature.key_id != payload["key_id"]
        or inventory.public_key_fingerprint != fingerprint
        or [transport.value for transport in inventory.transports] != ["local_process"]
        or inventory.attestation.value != "unverified"
    ):
        raise ValueError("worker inventory violates the physical-smoke contract profile")
    if document_sha256(inventory) != payload["inventory_sha256"]:
        raise ValueError("worker inventory digest is invalid")
    return inventory, public_key


def _resources() -> dict[str, int]:
    return {
        "cpu_millicores": 100,
        "memory_bytes": 1_048_576,
        "gpu_count": 0,
        "gpu_memory_bytes": 0,
        "storage_bytes": 1_048_576,
        "ingress_bps": 0,
        "egress_bps": 0,
    }


def _parameters() -> dict[str, Any]:
    return {
        "batch_size": None,
        "max_tokens": None,
        "temperature": 0.0,
        "top_k": None,
        "seed": 0,
        "precision": None,
        "checkpoint_interval_seconds": None,
        "replica_count": None,
        "chunk_size": None,
        "width": None,
        "height": None,
        "steps": None,
        "deterministic": True,
    }


def _build_request(
    *,
    account_id: str,
    node_id: str,
    controller: Ed25519DocumentSigner,
    now: datetime,
    run_token: str,
    bundle: bytes,
) -> ChalRequest:
    slug = hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:12]
    digest = hashlib.sha256(bundle).hexdigest()
    payload = {
        "schema": "planetary.chal.request.v1",
        "request_id": f"request:physical-smoke:{run_token}:{slug}",
        "trace_id": f"trace:physical-smoke:{run_token}:{slug}",
        "parent_request_id": None,
        "issued_at": _wire_time(now),
        "ttl_seconds": 300,
        "idempotency_key": f"idempotency:physical-smoke:{run_token}:{slug}",
        "account_id": account_id,
        "capability_id": f"capability:physical-smoke:{run_token}:{slug}",
        "device_uri": f"chal://private-mesh/{slug}/hash",
        "workload_kind": "evaluation",
        "workload_manifest": {
            "uri": f"artifact://private-mesh/bundle/{digest}",
            "sha256": digest,
            "size_bytes": len(bundle),
            "media_type": "application/octet-stream",
            "classification": "private",
        },
        "inputs": [],
        "parameters": _parameters(),
        "constraints": {
            "resources": _resources(),
            "latency_budget_ms": 30_000,
            "grounding_required": False,
            "template_leakage_allowed": False,
            "network_access": "none",
            "checkpoint_required": False,
        },
    }
    return sign_contract_document(ChalRequest, payload, controller)


def _build_capability(
    *,
    account_id: str,
    subject_id: str,
    node_id: str,
    controller: Ed25519DocumentSigner,
    now: datetime,
    run_token: str,
) -> CapabilityDocument:
    slug = hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:12]
    payload = {
        "schema": "planetary.chal.capability.v1",
        "capability_id": f"capability:physical-smoke:{run_token}:{slug}",
        "issuer_id": "controller:private-mesh",
        "subject_id": subject_id,
        "account_id": account_id,
        "audience_node_ids": [node_id],
        "actions": ["execute", "reserve"],
        "constraints": {
            "resources": _resources(),
            "minimum_attestation": "unverified",
            "workload_kinds": ["evaluation"],
            "transports": ["local_process"],
            "resource_prefixes": [f"chal://private-mesh/{slug}/"],
        },
        "not_before": _wire_time(now),
        "ttl_seconds": 600,
        "nonce": f"physicalsmoke{run_token}{slug}",
        "revocation_epoch": 0,
        "delegable": False,
    }
    return sign_contract_document(CapabilityDocument, payload, controller)


def _key_payload(record: KeyRecord) -> dict[str, Any]:
    return {
        "key_id": record.key_id,
        "public_key_base64": _b64url_encode(record.public_key_bytes()),
        "account_id": record.account_id,
        "audiences": sorted(record.audiences),
        "subject_id": record.subject_id,
        "node_id": record.node_id,
    }


def _fixed_bundle() -> bytes:
    prefix = b"$(touch /tmp/planetary-smoke-must-not-run); echo opaque; "
    return (prefix + b"#" * 128)[:128]


def _require_accepted(label: str, result: Any) -> None:
    if not result.accepted or result.status not in {
        VSourceStatus.ACCEPTED,
        VSourceStatus.IDEMPOTENT_REPLAY,
    }:
        raise RuntimeError(f"{label} was rejected: {result.status} {result.reason}")


def _bundle_manifest_sha256(bundle: bytes) -> str:
    """AIVM manifest digest (signature-omitted signing bytes) of the bundle."""

    from contracts.aivm.v1.canonical import document_sha256 as aivm_document_sha256

    return aivm_document_sha256(_strict_json(bundle))


def _validate_executor_outputs(
    *,
    response: ChalResponse,
    execution: dict[str, Any],
    request: ChalRequest,
    lease: LeaseDocument,
    target: NodeTarget,
    bundle: bytes,
) -> tuple[str, bytes, dict[str, Any]]:
    """Validate real-executor outputs: model result reference plus evidence."""

    report = _b64url_decode(execution["report_base64"])
    report_payload = _strict_json(report)
    report_sha256 = hashlib.sha256(report).hexdigest()
    if len(response.outputs) != 2:
        raise ValueError("executor response must contain result and evidence outputs")
    result_output, evidence_output = response.outputs
    if (
        evidence_output.sha256 != report_sha256
        or evidence_output.size_bytes != len(report)
        or evidence_output.media_type != AIVM_EVIDENCE_MEDIA_TYPE
    ):
        raise ValueError("executor evidence output does not match the returned report")
    if (
        result_output.media_type != "application/json"
        or result_output.uri != f"artifact://aivm/result/{result_output.sha256}"
    ):
        raise ValueError("executor result output is not a content-addressed result")
    if (
        report_payload.get("account_id") != lease.account_id
        or report_payload.get("node_id") != target.node_id
        or report_payload.get("lease_id") != lease.lease_id
        or report_payload.get("lease_sha256") != document_sha256(lease)
        or report_payload.get("fencing_token") != lease.fencing_token
        or report_payload.get("manifest_sha256") != _bundle_manifest_sha256(bundle)
        or not report_payload.get("workload_id")
        or not report_payload.get("entrypoint_id")
    ):
        raise ValueError("executor evidence does not bind the exact signed job")
    outputs = report_payload.get("outputs")
    if (
        not isinstance(outputs, list)
        or not outputs
        or outputs[0].get("sha256") != result_output.sha256
    ):
        raise ValueError("executor evidence outputs do not match the signed response")
    if request.workload_manifest.sha256 != hashlib.sha256(bundle).hexdigest():
        raise ValueError("signed request does not pin the executed bundle")
    return report_sha256, report, report_payload


def _ingest_result(
    *,
    service: LocalVSourceControlPlane,
    target: NodeTarget,
    enrollment: dict[str, Any],
    result: dict[str, Any],
    request: ChalRequest,
    capability: CapabilityDocument,
    lease: LeaseDocument,
    bundle: bytes,
    scheduler_key_id: str,
    scheduler_public_key: bytes,
    worker_trust_records: list[dict[str, Any]],
    workload_mode: str = "hash_report",
) -> dict[str, Any]:
    if set(result) != _RESULT_FIELDS or result["schema"] != "planetary.private_mesh.ssh_result.v1":
        raise ValueError("worker returned an unsupported result envelope")
    if result["node_id"] != target.node_id or result["hostname"] != enrollment["hostname"]:
        raise ValueError("worker execution identity changed after enrollment")
    admission = result["admission"]
    execution = result["execution"]
    if not isinstance(admission, dict) or admission.get("status") != "admitted" or admission.get("accepted") is not True:
        raise RuntimeError(f"worker {target.node_id} did not admit its signed lease")
    if not isinstance(execution, dict) or execution.get("status") != "executed" or execution.get("accepted") is not True:
        raise RuntimeError(f"worker {target.node_id} did not execute the bounded hash operation")
    if admission.get("error") is not None or execution.get("error") is not None:
        raise RuntimeError("successful worker result unexpectedly contains an error frame")
    admitted = _wire_model(LifecycleEvent, admission["lifecycle_event"])
    response = _wire_model(ChalResponse, execution["response"])
    lifecycle = [
        _wire_model(LifecycleEvent, value) for value in execution["lifecycle_events"]
    ]
    if [event.state for event in lifecycle] != [
        LifecycleState.STAGED,
        LifecycleState.RUNNING,
        LifecycleState.COMPLETED,
    ]:
        raise ValueError("worker lifecycle sequence is not admitted/staged/running/completed")
    validate_lease_bound_lifecycle(admitted, lease)
    validate_lease_bound_response(response, lease)
    for event in lifecycle:
        validate_lease_bound_lifecycle(event, lease)

    if workload_mode == "executor_evidence":
        report_sha256, report, report_payload = _validate_executor_outputs(
            response=response,
            execution=execution,
            request=request,
            lease=lease,
            target=target,
            bundle=bundle,
        )
    else:
        report = _b64url_decode(execution["report_base64"])
        report_payload = _strict_json(report)
        if rfc8785.dumps(report_payload) != report:
            raise ValueError("worker hash report is not RFC 8785 canonical JSON")
        report_sha256 = hashlib.sha256(report).hexdigest()
        if len(response.outputs) != 1:
            raise ValueError("worker response must contain exactly one bounded hash report")
        output = response.outputs[0]
        if (
            output.sha256 != report_sha256
            or output.size_bytes != len(report)
            or output.media_type != HASH_REPORT_MEDIA_TYPE
            or report_payload.get("schema") != HASH_REPORT_SCHEMA
            or report_payload.get("account_id") != lease.account_id
            or report_payload.get("node_id") != target.node_id
            or report_payload.get("request_id") != request.request_id
            or report_payload.get("request_sha256") != document_sha256(request)
            or report_payload.get("lease_id") != lease.lease_id
            or report_payload.get("lease_sha256") != document_sha256(lease)
            or report_payload.get("fencing_token") != lease.fencing_token
            or report_payload.get("bundle_sha256") != hashlib.sha256(bundle).hexdigest()
            or report_payload.get("bundle_size_bytes") != len(bundle)
        ):
            raise ValueError("worker hash report does not bind the exact physical-smoke job")

    _require_accepted("admitted lifecycle", service.record_lifecycle_event(admitted))
    _require_accepted("staged lifecycle", service.record_lifecycle_event(lifecycle[0]))
    _require_accepted("running lifecycle", service.record_lifecycle_event(lifecycle[1]))
    _require_accepted("signed response", service.record_response(response))
    _require_accepted("completed lifecycle", service.record_lifecycle_event(lifecycle[2]))
    released = service.get_lease(lease.lease_id)
    if released is None or released.state != LeaseState.RELEASED:
        raise RuntimeError("terminal lifecycle did not release the durable lease")
    if released.signature.key_id != scheduler_key_id:
        raise RuntimeError("released lease is not scheduler-signed")
    _verify_ed25519_document(
        lease,
        public_key=scheduler_public_key,
        expected_key_id=scheduler_key_id,
    )
    _verify_ed25519_document(
        released,
        public_key=scheduler_public_key,
        expected_key_id=scheduler_key_id,
    )

    return {
        "node_id": target.node_id,
        "hostname": result["hostname"],
        "node_key_fingerprint": enrollment["public_key_fingerprint"],
        "inventory_sha256": document_sha256(
            _wire_model(ResourceInventory, enrollment["inventory"])
        ),
        "request_sha256": document_sha256(request),
        "capability_sha256": document_sha256(capability),
        "active_lease_sha256": document_sha256(lease),
        "released_lease_sha256": document_sha256(released),
        "response_sha256": document_sha256(response),
        "lifecycle_sha256": [document_sha256(admitted)]
        + [document_sha256(event) for event in lifecycle],
        "report_sha256": report_sha256,
        "report_size_bytes": len(report),
        "worker_trust_records": worker_trust_records,
        "documents": {
            "inventory": enrollment["inventory"],
            "request": request.model_dump(mode="json", by_alias=True),
            "capability": capability.model_dump(mode="json", by_alias=True),
            "active_lease": lease.model_dump(mode="json", by_alias=True),
            "admitted": admitted.model_dump(mode="json", by_alias=True),
            "lifecycle": [event.model_dump(mode="json", by_alias=True) for event in lifecycle],
            "response": response.model_dump(mode="json", by_alias=True),
            "released_lease": released.model_dump(mode="json", by_alias=True),
            "report": report_payload,
        },
    }


def _prepare_state_db(path: Path) -> Path:
    requested = path.expanduser()
    if requested.exists() or requested.is_symlink():
        raise ValueError("persistent SQLite state path already exists")
    requested.parent.mkdir(parents=True, exist_ok=True)
    path = requested.parent.resolve() / requested.name
    if path.exists() or path.is_symlink():
        raise ValueError("persistent SQLite state path already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _checkpoint_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if result is None or result[0] != 0:
        raise RuntimeError("SQLite WAL checkpoint did not reach a stable snapshot")


def run_two_node_smoke(
    targets: list[NodeTarget],
    *,
    account_id: str,
    subject_id: str,
    carrier: SshCarrier,
    state_db_path: Path | None = None,
) -> dict[str, Any]:
    if len(targets) != 2:
        raise ValueError("physical smoke requires exactly two worker targets")
    _require_identifier("account_id", account_id)
    _require_identifier("subject_id", subject_id)
    if len({target.node_id for target in targets}) != 2:
        raise ValueError("physical smoke requires two distinct node IDs")
    if len({target.ssh_host_fingerprint for target in targets}) != 2:
        raise ValueError("physical smoke requires two distinct pinned SSH host keys")

    pins = [carrier.verify_pinned_host(target) for target in targets]
    with ThreadPoolExecutor(max_workers=2) as pool:
        enrollments = list(
            pool.map(
                lambda target: carrier.enroll(
                    target,
                    account_id=account_id,
                    subject_id=subject_id,
                ),
                targets,
            )
        )
    validated = [
        _validate_enrollment(target, enrollment, account_id=account_id)
        for target, enrollment in zip(targets, enrollments, strict=True)
    ]
    inventories = [item[0] for item in validated]
    public_keys = [item[1] for item in validated]
    if len({enrollment["hostname"] for enrollment in enrollments}) != 2:
        raise RuntimeError("SSH targets did not reach two distinct physical hostnames")
    if len({enrollment["public_key_fingerprint"] for enrollment in enrollments}) != 2:
        raise RuntimeError("physical workers do not have distinct node-local signing keys")

    run_token = secrets.token_hex(8)
    scheduler_id = f"scheduler:private-mesh:{run_token}"
    controller = _signer(f"key:controller:private-mesh:{run_token}")
    scheduler = _signer(f"key:scheduler:private-mesh:{run_token}")
    clock = SystemClock()
    resolver = MemoryResolver()
    controller_record = KeyRecord(
        key_id=controller.key_id,
        public_key=_signer_public_bytes(controller),
        account_id=account_id,
        audiences=(scheduler_id,),
        subject_id=subject_id,
    )
    resolver.add(controller_record)
    node_records: list[KeyRecord] = []
    for target, enrollment, public_key in zip(
        targets, enrollments, public_keys, strict=True
    ):
        record = KeyRecord(
            key_id=enrollment["key_id"],
            public_key=public_key,
            account_id=account_id,
            audiences=(scheduler_id,),
            subject_id=subject_id,
            node_id=target.node_id,
        )
        resolver.add(record)
        node_records.append(record)

    bundle = _fixed_bundle()
    persistent_state = state_db_path is not None
    if persistent_state:
        assert state_db_path is not None
        state_db_path = _prepare_state_db(state_db_path)
        state_context: Any = nullcontext(None)
    else:
        state_context = tempfile.TemporaryDirectory(
            prefix="planetary-physical-smoke-"
        )
    with state_context as directory:
        database_path = (
            state_db_path
            if state_db_path is not None
            else Path(directory) / "vsource.sqlite3"
        )
        assert database_path is not None
        service = LocalVSourceControlPlane(
            database_path,
            key_resolver=resolver,
            signer=scheduler,
            clock=clock,
            scheduler_id=scheduler_id,
        )
        for inventory in inventories:
            _require_accepted("signed inventory", service.register_inventory(inventory))

        jobs: list[tuple[ChalRequest, CapabilityDocument, LeaseDocument, dict[str, Any]]] = []
        now = clock.now()
        for target, inventory, node_record in zip(
            targets, inventories, node_records, strict=True
        ):
            request = _build_request(
                account_id=account_id,
                node_id=target.node_id,
                controller=controller,
                now=now,
                run_token=run_token,
                bundle=bundle,
            )
            capability = _build_capability(
                account_id=account_id,
                subject_id=subject_id,
                node_id=target.node_id,
                controller=controller,
                now=now,
                run_token=run_token,
            )
            allocation = service.allocate(
                request,
                capability,
                authenticated_subject_id=subject_id,
                lease_ttl_seconds=120,
            )
            _require_accepted("private-cell allocation", allocation)
            if (
                allocation.lease is None
                or allocation.placement is None
                or allocation.lease.node_id != target.node_id
                or allocation.lease.transport.value != "local_process"
            ):
                raise RuntimeError("scheduler did not allocate the exact intended node")
            scheduler_record = KeyRecord(
                key_id=scheduler.key_id,
                public_key=_signer_public_bytes(scheduler),
                account_id=account_id,
                audiences=(target.node_id,),
            )
            remote_controller_record = KeyRecord(
                key_id=controller.key_id,
                public_key=_signer_public_bytes(controller),
                account_id=account_id,
                audiences=(target.node_id,),
                subject_id=subject_id,
            )
            remote_node_record = KeyRecord(
                key_id=node_record.key_id,
                public_key=node_record.public_key_bytes(),
                account_id=account_id,
                audiences=(target.node_id,),
                subject_id=subject_id,
                node_id=target.node_id,
            )
            job = {
                "schema": "planetary.private_mesh.ssh_job.v1",
                "account_id": account_id,
                "node_id": target.node_id,
                "audience": target.node_id,
                "keys": sorted(
                    [
                        _key_payload(remote_controller_record),
                        _key_payload(scheduler_record),
                        _key_payload(remote_node_record),
                    ],
                    key=lambda value: value["key_id"],
                ),
                "inventory": inventory.model_dump(mode="json", by_alias=True),
                "request": request.model_dump(mode="json", by_alias=True),
                "capability": capability.model_dump(mode="json", by_alias=True),
                "lease": allocation.lease.model_dump(mode="json", by_alias=True),
                "bundle_base64": _b64url_encode(bundle),
            }
            jobs.append((request, capability, allocation.lease, job))

        with ThreadPoolExecutor(max_workers=2) as pool:
            remote_results = list(
                pool.map(
                    lambda item: carrier.execute(item[0], item[1][3]),
                    zip(targets, jobs, strict=True),
                )
            )
        node_evidence = [
            _ingest_result(
                service=service,
                target=target,
                enrollment=enrollment,
                result=result,
                request=job[0],
                capability=job[1],
                lease=job[2],
                bundle=bundle,
                scheduler_key_id=scheduler.key_id,
                scheduler_public_key=_signer_public_bytes(scheduler),
                worker_trust_records=job[3]["keys"],
            )
            for target, enrollment, result, job in zip(
                targets, enrollments, remote_results, jobs, strict=True
            )
        ]
        if persistent_state:
            os.chmod(database_path, 0o600)
            if stat.S_IMODE(database_path.stat().st_mode) != 0o600:
                raise RuntimeError("persistent SQLite state is not mode 0600")
        _checkpoint_sqlite(database_path)
        database_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()

    scheduler_record = KeyRecord(
        key_id=scheduler.key_id,
        public_key=_signer_public_bytes(scheduler),
        account_id=account_id,
        audiences=(scheduler_id,),
    )

    return {
        "schema": "planetary.private_mesh.physical_smoke_evidence.v1",
        "passed": True,
        "completed_at": _wire_time(clock.now()),
        "run_token": run_token,
        "account_id": account_id,
        "subject_id": subject_id,
        "carrier": "ssh_stdio",
        "contract_transport": "local_process",
        "implementation_sha256": implementation_sha256(),
        "ssh_pins": pins,
        "trust_bundle": {
            "scheduler_id": scheduler_id,
            "controller": _key_payload(controller_record),
            "scheduler": _key_payload(scheduler_record),
            "nodes": [_key_payload(record) for record in node_records],
        },
        "sqlite_state": {
            "persistent": persistent_state,
            "path": str(state_db_path) if state_db_path is not None else None,
            "sha256": database_sha256,
        },
        "nodes": node_evidence,
        "claims": {
            "two_distinct_pinned_ssh_hosts": True,
            "two_distinct_node_signing_keys": True,
            "bounded_hash_execution": True,
            "signed_fenced_contract_chain": True,
            "transactional_sqlite_lifecycle_ingestion": True,
            "persistent_sqlite_state": persistent_state,
            "durable_lifecycle_ingestion": persistent_state,
            "persistent_issuer_enrollment_proven": False,
            "signed_node_metadata_attestation_proven": False,
            "unisync_mtls_proven": False,
            "hardware_attestation_proven": False,
            "production_ssi_proven": False,
            "arbitrary_model_execution_proven": False,
        },
        "capacity_note": (
            "Inventory RAM/free-disk values are host snapshots, not reservations; "
            "network capacity is intentionally advertised as zero for this hash-only gate."
        ),
    }


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    encoded = (
        json.dumps(evidence, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError("short write while creating physical-smoke evidence")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise RuntimeError("physical-smoke evidence file mode is not 0600")


@dataclass(frozen=True)
class RemoteWorkload:
    """One real executor workload to run on a single enrolled worker.

    ``bundle`` must be the exact canonical signed AIVM workload manifest.
    ``objects`` are ``(sha256, payload)`` artifacts the carrier must place in
    the worker's mesh inbox before execution; pass an empty tuple when the
    objects were already delivered over the Unisync mTLS transfer boundary
    and record that delivery separately.
    """

    bundle: bytes
    executor: dict[str, Any]
    objects: tuple[tuple[str, bytes], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.bundle, bytes) or not self.bundle:
            raise ValueError("remote workload bundle must be non-empty bytes")
        for digest, payload in self.objects:
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("remote workload object digest mismatch")


def run_remote_workload(
    target: NodeTarget,
    *,
    account_id: str,
    subject_id: str,
    carrier: SshCarrier,
    workload: RemoteWorkload,
    object_delivery: str = "carrier_seeded_inbox",
) -> dict[str, Any]:
    """Run one useful executor workload on one enrolled physical worker.

    The flow is the two-node smoke's admission chain for a single node with
    a v2 executor job: signed request/capability/lease from a real vSource
    control plane, artifact objects in the worker mesh inbox, node-agent
    admission, real AIVM execution behind the worker's Podman boundary, and
    coordinator-side validation of the signed response, lifecycle, result
    reference, and execution evidence.
    """

    _require_identifier("account_id", account_id)
    _require_identifier("subject_id", subject_id)
    if object_delivery not in {"carrier_seeded_inbox", "unisync_mtls"}:
        raise ValueError("object_delivery must name a supported mechanism")

    pin = carrier.verify_pinned_host(target)
    enrollment = carrier.enroll(target, account_id=account_id, subject_id=subject_id)
    inventory, public_key = _validate_enrollment(
        target, enrollment, account_id=account_id
    )

    if workload.objects:
        deliver = getattr(carrier, "deliver_objects", None)
        if deliver is None:
            raise RuntimeError(
                "carrier cannot deliver objects; transfer them over the Unisync "
                "mTLS boundary first and pass objects=()"
            )
        deliver(target, workload.objects)

    run_token = secrets.token_hex(8)
    scheduler_id = f"scheduler:private-mesh:{run_token}"
    controller = _signer(f"key:controller:private-mesh:{run_token}")
    scheduler = _signer(f"key:scheduler:private-mesh:{run_token}")
    clock = SystemClock()
    resolver = MemoryResolver()
    resolver.add(
        KeyRecord(
            key_id=controller.key_id,
            public_key=_signer_public_bytes(controller),
            account_id=account_id,
            audiences=(scheduler_id,),
            subject_id=subject_id,
        )
    )
    node_record = KeyRecord(
        key_id=enrollment["key_id"],
        public_key=public_key,
        account_id=account_id,
        audiences=(scheduler_id,),
        subject_id=subject_id,
        node_id=target.node_id,
    )
    resolver.add(node_record)

    with tempfile.TemporaryDirectory(prefix="planetary-remote-workload-") as directory:
        service = LocalVSourceControlPlane(
            Path(directory) / "vsource.sqlite3",
            key_resolver=resolver,
            signer=scheduler,
            clock=clock,
            scheduler_id=scheduler_id,
        )
        _require_accepted("signed inventory", service.register_inventory(inventory))
        now = clock.now()
        request = _build_request(
            account_id=account_id,
            node_id=target.node_id,
            controller=controller,
            now=now,
            run_token=run_token,
            bundle=workload.bundle,
        )
        capability = _build_capability(
            account_id=account_id,
            subject_id=subject_id,
            node_id=target.node_id,
            controller=controller,
            now=now,
            run_token=run_token,
        )
        allocation = service.allocate(
            request,
            capability,
            authenticated_subject_id=subject_id,
            lease_ttl_seconds=300,
        )
        _require_accepted("private-cell allocation", allocation)
        if allocation.lease is None or allocation.lease.node_id != target.node_id:
            raise RuntimeError("scheduler did not allocate the exact intended node")
        job = {
            "schema": "planetary.private_mesh.ssh_job.v2",
            "account_id": account_id,
            "node_id": target.node_id,
            "audience": target.node_id,
            "keys": sorted(
                [
                    _key_payload(
                        KeyRecord(
                            key_id=controller.key_id,
                            public_key=_signer_public_bytes(controller),
                            account_id=account_id,
                            audiences=(target.node_id,),
                            subject_id=subject_id,
                        )
                    ),
                    _key_payload(
                        KeyRecord(
                            key_id=scheduler.key_id,
                            public_key=_signer_public_bytes(scheduler),
                            account_id=account_id,
                            audiences=(target.node_id,),
                        )
                    ),
                    _key_payload(
                        KeyRecord(
                            key_id=node_record.key_id,
                            public_key=node_record.public_key_bytes(),
                            account_id=account_id,
                            audiences=(target.node_id,),
                            subject_id=subject_id,
                            node_id=target.node_id,
                        )
                    ),
                ],
                key=lambda value: value["key_id"],
            ),
            "inventory": inventory.model_dump(mode="json", by_alias=True),
            "request": request.model_dump(mode="json", by_alias=True),
            "capability": capability.model_dump(mode="json", by_alias=True),
            "lease": allocation.lease.model_dump(mode="json", by_alias=True),
            "bundle_base64": _b64url_encode(workload.bundle),
            "executor": dict(workload.executor),
        }
        remote_result = carrier.execute(target, job)
        node_evidence = _ingest_result(
            service=service,
            target=target,
            enrollment=enrollment,
            result=remote_result,
            request=request,
            capability=capability,
            lease=allocation.lease,
            bundle=workload.bundle,
            scheduler_key_id=scheduler.key_id,
            scheduler_public_key=_signer_public_bytes(scheduler),
            worker_trust_records=job["keys"],
            workload_mode="executor_evidence",
        )

    return {
        "schema": "planetary.private_mesh.remote_workload_evidence.v1",
        "passed": True,
        "completed_at": _wire_time(clock.now()),
        "run_token": run_token,
        "account_id": account_id,
        "subject_id": subject_id,
        "carrier": "ssh_stdio",
        "object_delivery": object_delivery,
        "implementation_sha256": implementation_sha256(),
        "ssh_pin": pin,
        "executor_profile": workload.executor.get("profile"),
        "bundle_sha256": hashlib.sha256(workload.bundle).hexdigest(),
        "claims": {
            "unisync_mtls_object_delivery": object_delivery == "unisync_mtls",
        },
        "node": node_evidence,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--node",
        action="append",
        required=True,
        help="NODE_ID|SSH_ALIAS|HOST_FINGERPRINT|PYTHON|REPO|STATE_DIR (repeat twice)",
    )
    parser.add_argument("--known-hosts", type=Path, default=Path("~/.ssh/known_hosts"))
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--account-id", default=ACCOUNT_DEFAULT)
    parser.add_argument("--subject-id", default=SUBJECT_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--state-db",
        type=Path,
        help="persistent SQLite evidence state (defaults to OUTPUT.sqlite3)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if not 5 <= arguments.timeout_seconds <= 300:
            raise ValueError("timeout must be between 5 and 300 seconds")
        targets = [NodeTarget.parse(value) for value in arguments.node]
        carrier = SshCarrier(
            known_hosts=arguments.known_hosts,
            identity_file=arguments.identity_file,
            timeout_seconds=arguments.timeout_seconds,
        )
        evidence = run_two_node_smoke(
            targets,
            account_id=arguments.account_id,
            subject_id=arguments.subject_id,
            carrier=carrier,
            state_db_path=(
                arguments.state_db
                if arguments.state_db is not None
                else Path(f"{arguments.output}.sqlite3")
            ),
        )
        _write_evidence(arguments.output, evidence)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "planetary.private_mesh.physical_smoke_error.v1",
                    "passed": False,
                    "error": type(exc).__name__,
                    "message": str(exc)[:512],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "schema": evidence["schema"],
                "passed": True,
                "output": str(arguments.output),
                "nodes": [node["node_id"] for node in evidence["nodes"]],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
