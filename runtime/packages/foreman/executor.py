import subprocess
from .audit import log_audit

class Executor:
    def __init__(self):
        self.valid_tokens = set()
        
    def generate_token(self, step_id: str) -> str:
        token = f"token_{step_id}_{id(self)}"
        self.valid_tokens.add((step_id, token))
        return token
        
    def execute_auto(self, step: dict, gate_decision: dict):
        if gate_decision["decision"] != "auto":
            raise ValueError("Cannot auto-execute a gated step")
        return self._run(step, gate_decision)
        
    def execute_gated(self, step: dict, gate_decision: dict, token: str):
        if (step["step_id"], token) not in self.valid_tokens:
            raise ValueError("Invalid or consumed approval token")
        # Consume the token (single-use)
        self.valid_tokens.remove((step["step_id"], token))
        
        return self._run(step, gate_decision, approver="human_user")
        
    def deny_gated(self, step: dict, gate_decision: dict, token: str):
        if (step["step_id"], token) not in self.valid_tokens:
            raise ValueError("Invalid or consumed approval token")
        # Consume token
        self.valid_tokens.remove((step["step_id"], token))
        
        log_audit({
            "step_id": step["step_id"],
            "command": step["command"],
            "decision": "denied",
            "approver": "human_user",
            "exit_code": None,
            "output_tail": "Denied by user",
            "schedule_violation": gate_decision["schedule_violation"],
            "outlier_flag": gate_decision["outlier_flag"]
        })
        
    def _run(self, step: dict, gate_decision: dict, approver=None):
        cmd = step["command"]
        cwd = step.get("cwd", "/tmp")
        
        try:
            result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=30)
            exit_code = result.returncode
            output_tail = (result.stdout + result.stderr)[-500:]
        except Exception as e:
            exit_code = -1
            output_tail = str(e)
            
        log_audit({
            "step_id": step["step_id"],
            "command": cmd,
            "decision": gate_decision["decision"],
            "approver": approver,
            "exit_code": exit_code,
            "output_tail": output_tail,
            "schedule_violation": gate_decision["schedule_violation"],
            "outlier_flag": gate_decision["outlier_flag"]
        })
        
        return exit_code, output_tail
