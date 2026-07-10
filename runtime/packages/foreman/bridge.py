from .privilege_model import decide
from .executor import Executor
from .schedule import validate_schedule

class ForemanBridge:
    def __init__(self):
        self.queue = {}
        self.executor = Executor()
        
    def submit_plan(self, plan: dict):
        schedule = {item["step_id"]: item for item in validate_schedule(plan)}
        
        for step in plan.get("steps", []):
            step_id = step["step_id"]
            declared_tier = schedule.get(step_id, {}).get("declared_tier", 0)
            effects = schedule.get(step_id, {}).get("declared_effects", {})
            
            gate_decision = decide(step, declared_tier)
            
            if gate_decision["decision"] == "auto":
                # Execute immediately
                self.executor.execute_auto(step, gate_decision)
            else:
                # Enqueue for human approval
                token = self.executor.generate_token(step_id)
                self.queue[step_id] = {
                    "step": step,
                    "gate_decision": gate_decision,
                    "token": token,
                    "queue_item": {
                        "step_id": step_id,
                        "command": step["command"],
                        "cwd": step.get("cwd"),
                        "declared_tier": declared_tier,
                        "detected_tier": gate_decision["detected_tier"],
                        "effects": effects,
                        "blast_radius": gate_decision["op_type"],
                        "status": "pending",
                        "reasons": gate_decision["reasons"],
                        "token": token
                    }
                }
                
    def get_queue(self):
        return [v["queue_item"] for v in self.queue.values()]
        
    def approve(self, step_id: str, token: str):
        if step_id not in self.queue:
            raise ValueError("Step not found in queue")
            
        item = self.queue.pop(step_id)
        self.executor.execute_gated(item["step"], item["gate_decision"], token)
        
    def deny(self, step_id: str, token: str):
        if step_id not in self.queue:
            raise ValueError("Step not found in queue")
            
        item = self.queue.pop(step_id)
        self.executor.deny_gated(item["step"], item["gate_decision"], token)

# Singleton bridge instance
bridge_instance = ForemanBridge()
