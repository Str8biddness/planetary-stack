import hashlib
import pytest
from pathlib import Path

from services.remote_backend import RemoteExecutionBackend
from services.private_mesh.ssh_smoke import SshCarrier, NodeTarget
from services.private_mesh.node_agent import NodeAgentStatus
from tests.private_mesh.test_execution_wiring import _wiring
from tests.vsource.test_local_control_plane import (
    allocate_once,
    capability_doc,
    request_doc,
    ACCOUNT,
    SUBJECT,
)

def test_remote_backend_success(tmp_path: Path):
    harness = _wiring(tmp_path, preadmit=False)
    ctx = harness.ctx
    
    # Build real signed documents from the harness context
    workload_digest = hashlib.sha256(harness.bundle).hexdigest()
    workload_size = len(harness.bundle)
    request = request_doc(ctx, workload_digest=workload_digest, workload_size=workload_size)
    capability = capability_doc(ctx)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    lease = allocation.lease

    # We will mock SshCarrier
    class MockSshCarrier:
        def execute(self, target, job):
            # simulate worker CLI locally!
            # The worker CLI parses the job and calls NodeAgent.admit_lease and execute
            agent = harness.agent
            admit = agent.admit_lease(job["lease"], job["request"], job["capability"], authenticated_subject_id=SUBJECT)
            if not admit.accepted:
                return {
                    "schema": "planetary.private_mesh.ssh_result.v1",
                    "hostname": "test",
                    "node_id": job["node_id"],
                    "admission": {"accepted": False, "reason": admit.reason},
                    "execution": None
                }
                
            import base64
            bundle = base64.urlsafe_b64decode(job["bundle_base64"] + "==")
            exec_res = agent.execute(
                lease_id=admit.lease_id,
                lease_sha256=admit.lease_sha256,
                fencing_token=job["lease"]["fencing_token"],
                bundle=bundle
            )
            
            return {
                "schema": "planetary.private_mesh.ssh_result.v1",
                "hostname": "test",
                "node_id": job["node_id"],
                "admission": {"accepted": True},
                "execution": {
                    "status": exec_res.status.value,
                    "accepted": exec_res.accepted,
                    "reason": exec_res.reason,
                    "response": exec_res.response.model_dump(mode="json", by_alias=True) if exec_res.response else None,
                    "lifecycle_events": [],
                    "report_base64": base64.urlsafe_b64encode(exec_res.report).rstrip(b"=").decode("ascii") if exec_res.report else None,
                    "error": None
                }
            }
            
    carrier = MockSshCarrier()
    target = NodeTarget("node:001", "alias", "SHA256:abcd", "/bin/python", "/repo", "/state")
    
    backend = RemoteExecutionBackend(
        carrier=carrier,
        target=target,
        account_id=ACCOUNT,
        keys=[],
        inventory={"schema": "planetary.vsource.inventory.v1"}
    )

    admit_res = backend.admit_lease(
        lease,
        request,
        capability,
        authenticated_subject_id=SUBJECT
    )
    assert admit_res.accepted
    assert admit_res.status == NodeAgentStatus.ADMITTED
    
    # execute
    exec_res = backend.execute(
        lease_id=admit_res.lease_id,
        lease_sha256=admit_res.lease_sha256,
        fencing_token=lease.fencing_token,
        bundle=harness.bundle,
    )
    assert exec_res.accepted
    assert exec_res.status == NodeAgentStatus.EXECUTED
    assert exec_res.response is not None

