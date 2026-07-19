"""Three-node private-mesh cell acceptance harness (checklist F-080/F-020).

This module generalizes the pinned-SSH two-node smoke coordinator in
``services.private_mesh.ssh_smoke`` to a three-enrolled-node cell in which a
single execution node runs one bounded ``ssh_job.v1`` hash workload behind a
scheduler-signed fenced lease.  It is an *orchestration harness with in-process
unit coverage*, not a physical cell acceptance run: the physical run on real
machines is performed separately by the operator.

The harness truthfully records ``contract_transport = local_process`` because
execution occurs inside the node-local worker process, and it records explicit
non-claims (``physical_cell_proven``, ``podman_model_execution``) so its
evidence can never be mistaken for the physical gate.

Reuses the two-node crypto/verification helpers rather than duplicating them.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    LeaseDocument,
    ResourceInventory,
)
from services.private_mesh.ssh_smoke import (
    MemoryResolver,
    NodeTarget,
    SystemClock,
    _b64url_encode,
    _build_capability,
    _build_request,
    _checkpoint_sqlite,
    _fixed_bundle,
    _ingest_result,
    _key_payload,
    _prepare_state_db,
    _require_accepted,
    _require_identifier,
    _signer,
    _signer_public_bytes,
    _validate_enrollment,
    _wire_model,
)
from services.private_mesh.worker_cli import implementation_sha256
from services.vsource import KeyRecord, LocalVSourceControlPlane


CELL_NODE_COUNT = 3


def _probe_member(
    carrier: Any,
    target: NodeTarget,
    enrollment: dict[str, Any],
    *,
    account_id: str,
    subject_id: str,
) -> tuple[bool, str]:
    """Best-effort post-allocation liveness probe of a non-execution member.

    Re-runs the idempotent enrollment through the carrier and confirms the node
    still reports the same signing identity and hostname.  Any carrier failure
    (a "disappeared" worker) is caught and reported as an explicit reason; the
    probe never fabricates a healthy result for an unreachable node.
    """

    try:
        again = carrier.enroll(
            target,
            account_id=account_id,
            subject_id=subject_id,
        )
    except Exception as exc:  # noqa: BLE001 - the carrier is untrusted transport
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"
    if (
        again.get("node_id") != enrollment["node_id"]
        or again.get("key_id") != enrollment["key_id"]
        or again.get("public_key_fingerprint") != enrollment["public_key_fingerprint"]
        or again.get("hostname") != enrollment["hostname"]
    ):
        return False, "member returned a different signed identity on re-probe"
    return True, "reachable"


def run_three_node_cell(
    targets: list[NodeTarget],
    *,
    account_id: str,
    subject_id: str,
    carrier: Any,
    execution_node_index: int = 0,
    state_db_path: Path | None = None,
    require_all_members_reachable: bool = False,
) -> dict[str, Any]:
    """Run a three-node cell acceptance flow with one execution node.

    All three targets are enrolled with distinct node ids/keys and their signed
    inventories are registered.  A scheduler-signed fenced lease is allocated on
    exactly one execution node, a bounded ``ssh_job.v1`` hash job is dispatched
    to it, and the signed response plus lifecycle are ingested and verified
    exactly as the two-node smoke does.

    After allocation the two non-execution members are liveness-probed.  If one
    has disappeared (its carrier raises), the cell still completes on the
    healthy execution node and records the member as degraded with an explicit
    reason -- unless ``require_all_members_reachable`` is set, in which case the
    cell fails closed with an explicit ``RuntimeError``.  A fabricated success
    for an unreachable member is never produced.
    """

    if len(targets) != CELL_NODE_COUNT:
        raise ValueError("cell acceptance requires exactly three worker targets")
    _require_identifier("account_id", account_id)
    _require_identifier("subject_id", subject_id)
    if not 0 <= execution_node_index < CELL_NODE_COUNT:
        raise ValueError("execution_node_index must select one of the three nodes")
    if len({target.node_id for target in targets}) != CELL_NODE_COUNT:
        raise ValueError("cell acceptance requires three distinct node IDs")
    if len({target.ssh_host_fingerprint for target in targets}) != CELL_NODE_COUNT:
        raise ValueError("cell acceptance requires three distinct pinned SSH host keys")

    pins = [carrier.verify_pinned_host(target) for target in targets]
    enrollments = [
        carrier.enroll(target, account_id=account_id, subject_id=subject_id)
        for target in targets
    ]
    validated = [
        _validate_enrollment(target, enrollment, account_id=account_id)
        for target, enrollment in zip(targets, enrollments, strict=True)
    ]
    inventories = [item[0] for item in validated]
    public_keys = [item[1] for item in validated]
    if len({enrollment["hostname"] for enrollment in enrollments}) != CELL_NODE_COUNT:
        raise RuntimeError("SSH targets did not reach three distinct physical hostnames")
    if (
        len({enrollment["public_key_fingerprint"] for enrollment in enrollments})
        != CELL_NODE_COUNT
    ):
        raise RuntimeError("cell workers do not have distinct node-local signing keys")

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

    execution_target = targets[execution_node_index]
    execution_enrollment = enrollments[execution_node_index]
    execution_inventory = inventories[execution_node_index]
    execution_record = node_records[execution_node_index]

    bundle = _fixed_bundle()
    persistent_state = state_db_path is not None
    if persistent_state:
        assert state_db_path is not None
        state_db_path = _prepare_state_db(state_db_path)
        state_context: Any = nullcontext(None)
    else:
        state_context = tempfile.TemporaryDirectory(prefix="planetary-cell-smoke-")

    member_health: list[dict[str, Any]] = []
    degraded = False
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

        now = clock.now()
        request: ChalRequest = _build_request(
            account_id=account_id,
            node_id=execution_target.node_id,
            controller=controller,
            now=now,
            run_token=run_token,
            bundle=bundle,
        )
        capability: CapabilityDocument = _build_capability(
            account_id=account_id,
            subject_id=subject_id,
            node_id=execution_target.node_id,
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
            or allocation.lease.node_id != execution_target.node_id
            or allocation.lease.transport.value != "local_process"
        ):
            raise RuntimeError("scheduler did not allocate the exact intended node")
        lease: LeaseDocument = allocation.lease

        # After allocation, probe the two non-execution members.  A disappeared
        # (carrier-raising) non-execution member degrades the cell but does not
        # block the healthy execution node; a fabricated success is never made.
        for index, (target, enrollment) in enumerate(
            zip(targets, enrollments, strict=True)
        ):
            if index == execution_node_index:
                member_health.append(
                    {
                        "node_id": target.node_id,
                        "role": "execution",
                        "reachable": True,
                        "reason": "execution node exercised by the dispatched job",
                    }
                )
                continue
            reachable, reason = _probe_member(
                carrier,
                target,
                enrollment,
                account_id=account_id,
                subject_id=subject_id,
            )
            member_health.append(
                {
                    "node_id": target.node_id,
                    "role": "member",
                    "reachable": reachable,
                    "reason": reason,
                }
            )
            if not reachable:
                degraded = True
                if require_all_members_reachable:
                    raise RuntimeError(
                        "cell failed closed: required cell member "
                        f"{target.node_id} is unreachable after allocation "
                        f"({reason})"
                    )

        scheduler_record = KeyRecord(
            key_id=scheduler.key_id,
            public_key=_signer_public_bytes(scheduler),
            account_id=account_id,
            audiences=(execution_target.node_id,),
        )
        remote_controller_record = KeyRecord(
            key_id=controller.key_id,
            public_key=_signer_public_bytes(controller),
            account_id=account_id,
            audiences=(execution_target.node_id,),
            subject_id=subject_id,
        )
        remote_node_record = KeyRecord(
            key_id=execution_record.key_id,
            public_key=execution_record.public_key_bytes(),
            account_id=account_id,
            audiences=(execution_target.node_id,),
            subject_id=subject_id,
            node_id=execution_target.node_id,
        )
        job = {
            "schema": "planetary.private_mesh.ssh_job.v1",
            "account_id": account_id,
            "node_id": execution_target.node_id,
            "audience": execution_target.node_id,
            "keys": sorted(
                [
                    _key_payload(remote_controller_record),
                    _key_payload(scheduler_record),
                    _key_payload(remote_node_record),
                ],
                key=lambda value: value["key_id"],
            ),
            "inventory": execution_inventory.model_dump(mode="json", by_alias=True),
            "request": request.model_dump(mode="json", by_alias=True),
            "capability": capability.model_dump(mode="json", by_alias=True),
            "lease": lease.model_dump(mode="json", by_alias=True),
            "bundle_base64": _b64url_encode(bundle),
        }

        remote_result = carrier.execute(execution_target, job)
        node_evidence = _ingest_result(
            service=service,
            target=execution_target,
            enrollment=execution_enrollment,
            result=remote_result,
            request=request,
            capability=capability,
            lease=lease,
            bundle=bundle,
            scheduler_key_id=scheduler.key_id,
            scheduler_public_key=_signer_public_bytes(scheduler),
            worker_trust_records=job["keys"],
        )

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

    members = []
    for target, enrollment, health in zip(
        targets, enrollments, member_health, strict=True
    ):
        members.append(
            {
                "node_id": target.node_id,
                "hostname": enrollment["hostname"],
                "node_key_fingerprint": enrollment["public_key_fingerprint"],
                "inventory_sha256": document_sha256(
                    _wire_model(ResourceInventory, enrollment["inventory"])
                ),
                "role": health["role"],
                "reachable": health["reachable"],
                "health_reason": health["reason"],
                "is_execution_node": target.node_id == execution_target.node_id,
            }
        )

    return {
        "schema": "planetary.private_mesh.cell_smoke_evidence.v1",
        "passed": True,
        "degraded": degraded,
        "completed_at": clock.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_token": run_token,
        "account_id": account_id,
        "subject_id": subject_id,
        "carrier": "ssh_stdio",
        "contract_transport": "local_process",
        "implementation_sha256": implementation_sha256(),
        "node_count": CELL_NODE_COUNT,
        "execution_node": execution_target.node_id,
        "ssh_pins": pins,
        "members": members,
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
        "execution": node_evidence,
        "claims": {
            "three_enrolled_nodes": True,
            "three_distinct_pinned_ssh_hosts": True,
            "three_distinct_node_signing_keys": True,
            "single_execution_node_fenced_lease": True,
            "bounded_hash_execution": True,
            "signed_fenced_contract_chain": True,
            "transactional_sqlite_lifecycle_ingestion": True,
            "persistent_sqlite_state": persistent_state,
            "worker_disappearance_tolerated_or_failed_closed": True,
            # Explicit non-claims: this harness proves orchestration logic only.
            "physical_cell_proven": False,
            "podman_model_execution": False,
            "unisync_mtls_proven": False,
            "hardware_attestation_proven": False,
            "production_ssi_proven": False,
            "arbitrary_model_execution_proven": False,
        },
        "harness_note": (
            "This is the in-process cell orchestration harness (LocalCarrier / "
            "unit-tested logic). It does not run physical machines; the physical "
            "three-node acceptance is performed separately by the operator."
        ),
    }
