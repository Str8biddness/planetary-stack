"""Reproducible physical demo: browser->job->worker execution->result pull.

Server-side driver for the owner's LAN mesh. It builds a real signed-request
workload bundle, enrolls the worker over pinned SSH, submits the job (the worker
executes the real text-classification model in rootless Podman), and returns the
verified result to THIS desktop via the firewall-free desktop-initiated pull
(the desktop dials outbound; no inbound port). The Web Desktop's POST /api/jobs
and GET /api/jobs/<id>/results/<sha> call exactly these two pipeline methods.

Machine-specific constants below (worker alias/IP/paths, image digest) describe
the owner's cell; change them for another deployment. Input artifacts are staged
into the worker inbox directly here — mTLS INPUT delivery is separately proven
(F020_MESH_WORKLOAD); this harness focuses on execute->result->pull->present.
"""

import hashlib
import json
import secrets
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/dakin/planetary-stack-finish")
sys.path.insert(0, "/home/dakin/planetary-stack-finish/apps/synthesus/runtime/packages")

from contracts.aivm.v1 import AIVMWorkloadManifest, canonical_document_bytes
from services.private_mesh.ssh_smoke import NodeTarget
from services.remote_pipeline import build_remote_pipeline
from services.remote_worker_config import RemoteWorkerConfig
from services.result_transfer import build_pull_result_loader
from services.unisync.mesh_smoke import HybridMeshCarrier

HEAD = "19b50a6fd58ee0a5f3ba93db1a520b3a89ccf0e1"
KH = Path("/home/dakin/.claude/jobs/adcb2aa2/tmp/mesh_known_hosts")
IDENT = Path("/home/dakin/.ssh/id_ed25519")
WORKER_REPO = f"/home/dakin/ps-demo-{HEAD}"
WORKER_PY = "/home/dakin/planetary-stack-b/.venv/bin/python"
EXEC_STATE = "/home/dakin/ps-demo-exec"
ACCOUNT = "account:private-mesh:home"
SUBJECT = "subject:private-mesh:owner"
NODE = "node:private-mesh:dakin-ms-7c95"
IMAGE_DIGEST = "sha256:4933984efd51622d198bab953d5011cdc6b94155a2467e85acbd8e1e581a3f5b"
IMAGE_REF = f"localhost/aivm-text-classify@{IMAGE_DIGEST}"
MODEL_SHA = "575d566648d21bcfae72241fb0d74e3d95ae22f3d44c28baab0cd579e38b817d"
DOC_SHA = "07a1c31caa4e70ed6c41a318f9559bcb6780bf735fc6e6078a99565db1d12dd1"


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_bundle() -> bytes:
    now = datetime.now(UTC).replace(microsecond=0)
    wire = {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:demo:001",
        "account_id": ACCOUNT,
        "workload_id": "workload:demo:001",
        "issued_at": _iso(now - timedelta(minutes=5)),
        "expires_at": _iso(now + timedelta(minutes=25)),
        "signer_key_id": "key:owner:001",
        "runtime_image": {
            "image_id": "aivm-text-classify",
            "digest": IMAGE_DIGEST,
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "user": "aivm",
            "privileged": False,
            "host_network": False,
            "host_pid": False,
            "host_ipc": False,
            "devices": [],
        },
        "entrypoint_id": "aivm.model.text-classify.v1",
        "resources": {
            "cpu_millicores": 1000,
            "memory_bytes": 268_435_456,
            "time_limit_seconds": 30,
            "process_limit": 16,
            "open_file_limit": 64,
            "output_bytes": 4096,
            "scratch_bytes": 0,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
        },
        "filesystem": {"rootfs": "readonly", "writable_paths": [], "host_mounts": []},
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": "artifact:document:001",
                "uri": "artifact://private/document",
                "kind": "input",
                "sha256": DOC_SHA,
                "size_bytes": 41,
                "media_type": "text/plain",
                "content_encoding": "identity",
                "created_at": _iso(now - timedelta(minutes=5)),
                "mount_path": "/work/input/document.txt",
                "readonly": True,
            },
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": "artifact:model:001",
                "uri": "artifact://private/model",
                "kind": "model",
                "sha256": MODEL_SHA,
                "size_bytes": 2354,
                "media_type": "application/octet-stream",
                "content_encoding": "identity",
                "created_at": _iso(now - timedelta(minutes=5)),
                "mount_path": "/work/input/model.onnx",
                "readonly": True,
            },
        ],
        "inputs": ["artifact:document:001", "artifact:model:001"],
        "outputs": ["output:classification:001"],
        "signature": {"algorithm": "ed25519", "key_id": "key:owner:001", "value": "A" * 86},
    }
    manifest = AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))
    return canonical_document_bytes(manifest)


def _ssh(cmd: str) -> tuple[int, str]:
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "dakin-MS-7C95", cmd],
                       capture_output=True, text=True, timeout=90)
    return p.returncode, p.stdout


def _make_pull_loader():
    def stage_on_worker(digest, source_state_dir):
        job = json.dumps({"schema": "planetary.private_mesh.stage_result.v1",
                          "account_id": ACCOUNT, "node_id": NODE, "result_sha256": digest})
        cmd = (f"set -e; mkdir -m 0700 -p {source_state_dir}/aivm/results; "
               f"cp {EXEC_STATE}/aivm/results/{digest} {source_state_dir}/aivm/results/{digest}; "
               f"printf %s {json.dumps(job)} | env PYTHONPATH={WORKER_REPO} {WORKER_PY} "
               f"-m services.private_mesh.worker_cli stage-result --state-dir {source_state_dir}; "
               f"chmod 0700 {source_state_dir}")
        rc, out = _ssh(cmd)
        if rc != 0:
            return None
        for line in out.splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("object_sha256") == digest:
                return int(o["byte_length"])
        return None

    return build_pull_result_loader(
        stage_on_worker=stage_on_worker,
        worker_source_dir_factory=lambda: f"/home/dakin/ps-demo-pull-{secrets.token_hex(6)}",
        cleanup_worker_dir=lambda p: _ssh(f"rm -rf {p}"),
        carrier=HybridMeshCarrier(known_hosts=KH, identity_file=IDENT, timeout_seconds=60),
        workspace=Path("/home/dakin/.claude/jobs/adcb2aa2/tmp/demo-pull-workspace"),
        account_id=ACCOUNT, subject_id=SUBJECT,
        worker_node_id=NODE, worker_python=WORKER_PY, worker_repo=WORKER_REPO,
        worker_ssh_alias="dakin-MS-7C95",
        worker_ssh_fingerprint="SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w",
        worker_listen_ip="192.168.68.54",
        desktop_node_id="node:desktop:001",
        desktop_python="/home/dakin/.local/share/synthesus/.venv/bin/python",
        desktop_repo="/home/dakin/planetary-stack-finish",
        desktop_san="desktop.mesh",
    )


def main():
    bundle = build_bundle()
    print("bundle sha256:", hashlib.sha256(bundle).hexdigest(), "len:", len(bundle))
    target = NodeTarget(NODE, "dakin-MS-7C95",
                        "SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w",
                        WORKER_PY, WORKER_REPO, EXEC_STATE)
    config = RemoteWorkerConfig(target=target, account_id=ACCOUNT, subject_id=SUBJECT,
                                image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST,
                                known_hosts=KH, ssh_identity=IDENT)
    loader = _make_pull_loader()
    pipeline = build_remote_pipeline(
        config,
        state_dir=Path("/home/dakin/.claude/jobs/adcb2aa2/tmp/demo-authority"),
        clock=lambda: datetime.now(UTC).replace(microsecond=0),
        result_loader=loader,
    )
    if pipeline is None:
        print("PIPELINE UNAVAILABLE (worker did not enroll)")
        return 1
    print("pipeline built + worker enrolled")
    record = pipeline.submit(bundle=bundle, workload_kind="evaluation")
    wire = record.to_wire()
    print("job_id:", wire.get("job_id"), "state:", wire.get("state"))
    outputs = wire.get("outputs") or []
    print("outputs:", [(o.get("sha256"), o.get("media_type")) for o in outputs])
    if wire.get("state") != "completed" or not outputs:
        print("JOB NOT COMPLETED:", json.dumps(wire)[:500])
        return 2
    out_sha = outputs[0]["sha256"]
    loaded = pipeline.result(wire["job_id"], out_sha)
    if loaded is None:
        print("RESULT PULL RETURNED None")
        return 3
    data, media = loaded
    print("PULLED RESULT bytes:", len(data), "media:", media)
    print("content:", data.decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
