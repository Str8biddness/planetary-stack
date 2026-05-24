"""
AutonomousRemediator — Self-Healing Security Operations for Synthesus 4.0.

Executes remediation actions to contain threats and restore system integrity.
All actions must be validated by SecurityGuardrails.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class AutonomousRemediator:
    """
    Handles the execution of security remediations.
    """
    def __init__(self, guardrails: Any):
        self.guardrails = guardrails
        self.history: List[Dict[str, Any]] = []

    def execute_remediation(self, action: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates and executes a remediation action.
        """
        # 1. Validate with Guardrails
        is_safe, reason = self.guardrails.validate_action(action, context)
        
        if not is_safe:
            msg = f"Remediation '{action}' BLOCKED by guardrails: {reason}"
            logger.warning(msg)
            self._record(action, context, "blocked", reason)
            return False, msg

        # 2. Execute Action (Simulation of system commands)
        logger.info(f"Executing remediation: {action}...")
        
        success = True
        execution_msg = ""

        try:
            if action == "block_ip":
                ip = context.get("target_ip", "unknown")
                execution_msg = f"Successfully blocked IP {ip} via firewall."
            elif action == "isolate_system":
                execution_msg = "System network isolation activated. Only secure management traffic allowed."
            elif action == "kill_process":
                pid = context.get("pid", "unknown")
                execution_msg = f"Terminated suspicious process PID {pid}."
            elif action == "rollback_file":
                file_path = context.get("file_path", "unknown")
                execution_msg = f"Restored {file_path} from secure baseline backup."
            else:
                success = False
                execution_msg = f"Unknown action: {action}"
        except Exception as e:
            success = False
            execution_msg = f"Execution failed: {e}"

        status = "success" if success else "failed"
        self._record(action, context, status, execution_msg)
        
        if success:
            logger.info(execution_msg)
        else:
            logger.error(execution_msg)

        return success, execution_msg

    def _record(self, action: str, context: Dict[str, Any], status: str, result: str):
        self.history.append({
            "timestamp": time.time(),
            "action": action,
            "context": context,
            "status": status,
            "result": result
        })

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return sorted(self.history, key=lambda x: x["timestamp"], reverse=True)[:limit]

    async def handle_incident(self, incident: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyzes an incident and attempts autonomous remediation.
        """
        results = []
        confidence = incident.get("confidence", 0.0)
        
        # Determine recommended action from guardrails
        recommendation = self.guardrails.get_recommendation(incident)
        
        if recommendation:
            logger.info(f"Remediator: Incident {incident['id']} triggered recommendation: {recommendation}")
            success, msg = self.execute_remediation(recommendation, incident)
            results.append({"action": recommendation, "success": success, "message": msg})
        
        # Specific heuristic remediations
        if confidence > 0.9:
            # Emergency lockdown for near-certain breaches
            success, msg = self.execute_remediation("isolate_system", incident)
            results.append({"action": "isolate_system", "success": success, "message": msg})
            
        return results
