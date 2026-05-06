# control_plane/device_manager.py

from typing import List, Dict, Any, Optional
import uuid
import os

class DeviceManager:
    def __init__(self):
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.approvals: Dict[str, Dict[str, Any]] = {}
        # Auto-enroll local if LOCAL_AI_VM_HOST=true
        local_ai_vm = os.environ.get("LOCAL_AI_VM_HOST", "false").lower() == "true"
        if local_ai_vm:
            self.add_device("localhost", "Local AI VM Host", "linux", "enrolled")

    def list_devices(self) -> Dict[str, Any]:
        return {"devices": list(self.devices.values())}

    def enroll_device(self, device_id: str, requested_scopes: List[str]) -> Dict[str, Any]:
        if device_id not in self.devices:
            return {"error": "device_not_found"}
        approval_id = str(uuid.uuid4())
        self.approvals[approval_id] = {
            "id": approval_id,
            "device_id": device_id,
            "description": f"Enroll device {device_id} for scopes {requested_scopes}",
            "requested_scopes": requested_scopes,
            "status": "pending",
            "type": "device_enrollment"
        }
        return {"approval_id": approval_id, "message": "Enrollment started, pending approval."}

    def list_approvals(self) -> Dict[str, Any]:
        return {"approvals": list(self.approvals.values())}

    def resolve_approval(self, approval_id: str, decision: str, remember_policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if approval_id not in self.approvals:
            return {"error": "approval_not_found"}
        approval = self.approvals[approval_id]
        if decision == "approve":
            device_id = approval["device_id"]
            if device_id in self.devices:
                self.devices[device_id]["status"] = "enrolled"
                # Add capabilities
                if self.devices[device_id].get("type") == "linux":
                    self.devices[device_id]["capabilities"] = ["ai_vm_host", "emulation_supported"]
                else:
                    self.devices[device_id]["capabilities"] = ["emulation_supported"]
            approval["status"] = "approved"
        elif decision == "deny":
            approval["status"] = "denied"
        else:
            return {"error": "invalid_decision"}
        if remember_policy:
            approval["remember_policy"] = remember_policy
        return {"message": "Approval resolved.", "device_id": approval["device_id"]}

    def add_device(self, device_id: str, name: str, device_type: str, status: str = "discovered"):
        self.devices[device_id] = {
            "id": device_id,
            "name": name,
            "type": device_type,
            "status": status,
            "capabilities": []
        }

    def start_ai_vm_host_setup(self, device_id: str, requested_scopes: List[str]) -> Dict[str, Any]:
        if device_id not in self.devices or self.devices[device_id]["status"] != "enrolled":
            return {"error": "device_not_enrolled"}
        approval_id = str(uuid.uuid4())
        summary = f"Setup AI VM host on {device_id}: install Docker if needed, pull Synthesus image, start container with scopes {requested_scopes}."
        self.approvals[approval_id] = {
            "id": approval_id,
            "device_id": device_id,
            "description": f"AI VM host setup for {device_id}",
            "requested_scopes": requested_scopes,
            "summary": summary,
            "status": "pending",
            "type": "ai_vm_host_setup"
        }
        return {"approval_id": approval_id, "message": "AI VM host setup started, pending approval."}

    def start_ai_vm_host_setup(self, device_id: str, requested_scopes: List[str]) -> Dict[str, Any]:
        if device_id not in self.devices or self.devices[device_id]["status"] != "enrolled":
            return {"error": "device_not_enrolled"}
        approval_id = str(uuid.uuid4())
        summary = f"Setup AI VM host on {device_id}: install Docker if needed, pull Synthesus image, start container with scopes {requested_scopes}."
        self.approvals[approval_id] = {
            "id": approval_id,
            "device_id": device_id,
            "description": f"AI VM host setup for {device_id}",
            "requested_scopes": requested_scopes,
            "summary": summary,
            "status": "pending",
            "type": "ai_vm_host_setup"
        }
        return {"approval_id": approval_id, "message": "AI VM host setup started, pending approval."}
