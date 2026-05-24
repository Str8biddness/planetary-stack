# amplification_wrapper.py
# Python wrapper to call AmplificationPlane TypeScript layer via Node.js subprocess
# Provides graceful fallback if Node.js/TypeScript is unavailable

import subprocess
import json
import os
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TS_NODE_CMD = ["npx", "ts-node", "scripts/amplifyCli.ts"]

@dataclass
class AmplificationContext:
    compute_budget: int = 50
    session_id: str = "default-session"
    domain: str = "chat"
    allowed_organs: Optional[List[str]] = None

@dataclass
class IntakeResult:
    summaries: List[Dict] = field(default_factory=list)
    anomaly_flags: List[Dict] = field(default_factory=list)

@dataclass
class PlanningResult:
    ranked_actions: List[Dict] = field(default_factory=list)
    top_trajectories: List[Dict] = field(default_factory=list)
    references: List[Dict] = field(default_factory=list)

@dataclass
class OutputResult:
    sanity_check_passed: bool = True
    operator_explanation: str = ""
    internal_summary: str = ""
    execution_recommendation: str = "PROCEED"  # PROCEED, REQUEST_CONFIRMATION, HALT

class AmplificationPlane:
    """
    Wrapper to call the TypeScript AmplificationPlane.
    Falls back to safe defaults if Node/TS is unavailable.
    """

    def __init__(self, ts_node_cmd: Optional[List[str]] = None, enabled: bool = True):
        self.ts_node_cmd = ts_node_cmd or TS_NODE_CMD
        self.enabled = enabled
        self._available: Optional[bool] = None
        self._consecutive_failures = 0
        self._circuit_breaker_until = 0.0

    def _is_available(self) -> bool:
        """Check if Node.js and ts-node are available."""
        if not self.enabled:
            return False
            
        import time
        if time.time() < self._circuit_breaker_until:
            return False
            
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run(
                ["npx", "ts-node", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT
            )
            self._available = result.returncode == 0
        except Exception as e:
            logger.warning(f"AmplificationPlane not available: {e}")
            self._available = False
        return self._available

    def _call_ts(self, phase: str, payload: Dict, retries: int = 2) -> Dict:
        """Call the TypeScript CLI with the given phase and payload, with retries and circuit breaking."""
        import time
        if not self.enabled or not self._is_available():
            raise RuntimeError("AmplificationPlane not enabled, unavailable, or circuit broken")

        cmd = self.ts_node_cmd + [phase, json.dumps(payload)]
        
        last_exception = None
        for attempt in range(retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=PROJECT_ROOT
                )
                if result.returncode != 0:
                    logger.error(f"AmplificationPlane {phase} error (attempt {attempt+1}): {result.stderr}")
                    raise RuntimeError(f"AmplificationPlane {phase} failed: {result.stderr}")
                
                # Success
                self._consecutive_failures = 0
                return json.loads(result.stdout)
            except subprocess.TimeoutExpired as e:
                logger.warning(f"AmplificationPlane {phase} timed out (attempt {attempt+1})")
                last_exception = e
            except json.JSONDecodeError as e:
                logger.error(f"AmplificationPlane {phase} returned invalid JSON: {e}")
                last_exception = e
            except Exception as e:
                logger.error(f"AmplificationPlane {phase} unexpected error: {e}")
                last_exception = e
                
            # Backoff before retry
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                
        # If we exhausted retries
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            logger.error("AmplificationPlane circuit breaker tripped! Disabling for 60 seconds.")
            self._circuit_breaker_until = time.time() + 60.0
            
        raise RuntimeError(f"AmplificationPlane {phase} exhausted retries") from last_exception

    def amplify_intake(self, ctx: AmplificationContext, world_state: Dict, raw_input: Any) -> IntakeResult:
        """
        Intake amplification: summarize and detect anomalies.
        Graceful fallback returns empty summaries/flags.
        """
        try:
            payload = {
                "computeBudget": ctx.compute_budget,
                "sessionId": ctx.session_id,
                "domain": ctx.domain,
                "allowedOrgans": ctx.allowed_organs,
                "worldState": world_state,
                "rawInput": raw_input,
            }
            result = self._call_ts("intake", payload)
            return IntakeResult(
                summaries=result.get("summaries", []),
                anomaly_flags=result.get("anomalyFlags", [])
            )
        except Exception as e:
            logger.warning(f"amplify_intake fallback: {e}")
            return IntakeResult()

    async def amplify_intake_async(self, ctx: AmplificationContext, world_state: Dict, raw_input: Any) -> IntakeResult:
        import asyncio
        return await asyncio.to_thread(self.amplify_intake, ctx, world_state, raw_input)

    def amplify_planning(self, ctx: AmplificationContext, world_state: Dict, candidate_actions: List[Dict]) -> PlanningResult:
        """
        Planning amplification: rank actions and estimate trajectories.
        Graceful fallback returns empty ranked actions.
        """
        try:
            payload = {
                "computeBudget": ctx.compute_budget,
                "sessionId": ctx.session_id,
                "domain": ctx.domain,
                "allowedOrgans": ctx.allowed_organs,
                "worldState": world_state,
                "candidateActions": candidate_actions,
            }
            result = self._call_ts("planning", payload)
            return PlanningResult(
                ranked_actions=result.get("rankedActions", []),
                top_trajectories=result.get("topTrajectories", []),
                references=result.get("references", [])
            )
        except Exception as e:
            logger.warning(f"amplify_planning fallback: {e}")
            return PlanningResult()

    async def amplify_planning_async(self, ctx: AmplificationContext, world_state: Dict, candidate_actions: List[Dict]) -> PlanningResult:
        import asyncio
        return await asyncio.to_thread(self.amplify_planning, ctx, world_state, candidate_actions)

    def amplify_output(self, ctx: AmplificationContext, chosen_action: Dict, updated_world: Dict, generation_trace: Optional[Any] = None) -> OutputResult:
        """
        Output amplification: sanity check and autonomy enforcement.
        Incorporates Probabilistic Generation Trace metrics.
        """
        try:
            payload = {
                "computeBudget": ctx.compute_budget,
                "sessionId": ctx.session_id,
                "domain": ctx.domain,
                "allowedOrgans": ctx.allowed_organs,
                "chosenAction": chosen_action,
                "updatedWorld": updated_world,
                "generationTrace": {
                    "text": generation_trace.text if generation_trace else None,
                    "confidence": getattr(generation_trace, 'mean_logprob', None) if generation_trace else None,
                    "satisfied": getattr(generation_trace, 'constraints_satisfied', True) if generation_trace else True,
                    "tokens_generated": len(getattr(generation_trace, 'token_logprobs', [])) if generation_trace else 0
                } if generation_trace else None
            }
            result = self._call_ts("output", payload)
            return OutputResult(
                sanity_check_passed=result.get("sanityCheckPassed", True),
                operator_explanation=result.get("operatorExplanation", ""),
                internal_summary=result.get("internalSummary", ""),
                execution_recommendation=result.get("executionRecommendation", "REQUEST_CONFIRMATION")
            )
        except Exception as e:
            logger.warning(f"amplify_output fallback: {e}")
            # Safe fallback: request confirmation
            return OutputResult(
                sanity_check_passed=True,
                operator_explanation="AmplificationPlane unavailable; proceeding with caution",
                internal_summary="Fallback executed",
                execution_recommendation="REQUEST_CONFIRMATION"
            )

    async def amplify_output_async(self, ctx: AmplificationContext, chosen_action: Dict, updated_world: Dict, generation_trace: Optional[Any] = None) -> OutputResult:
        import asyncio
        return await asyncio.to_thread(self.amplify_output, ctx, chosen_action, updated_world, generation_trace)

# Singleton instance for convenience
_default_plane: Optional[AmplificationPlane] = None

def get_amplification_plane(enabled: bool = True) -> AmplificationPlane:
    """Get or create the default AmplificationPlane instance."""
    global _default_plane
    if _default_plane is None:
        _default_plane = AmplificationPlane(enabled=enabled)
    return _default_plane

def reset_amplification_plane():
    """Reset the default instance (useful for testing)."""
    global _default_plane
    _default_plane = None
