from __future__ import annotations
import asyncio
import logging
import functools
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from ..kernel.npc import NPC

logger = logging.getLogger("aivm.isolation")


@dataclass(frozen=True)
class DeviceExecutionResult:
    """Traceable result for a guarded CHAL/AIVM device dispatch."""
    device_id: str
    ok: bool
    status: str
    latency_ms: float
    output: Any = None
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "ok": self.ok,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class AIVMExecutionGuard:
    """Bound async/sync virtual device calls with timeout and fault isolation."""

    async def run(
        self,
        device_id: str,
        operation: Callable[[], Any],
        *,
        timeout_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeviceExecutionResult:
        start = time.perf_counter()
        try:
            output = await asyncio.wait_for(
                self._invoke(operation),
                timeout=max(timeout_ms, 1.0) / 1000.0,
            )
            return DeviceExecutionResult(
                device_id=device_id,
                ok=True,
                status="ok",
                latency_ms=(time.perf_counter() - start) * 1000,
                output=output,
                metadata=metadata or {},
            )
        except asyncio.TimeoutError:
            return DeviceExecutionResult(
                device_id=device_id,
                ok=False,
                status="timeout",
                latency_ms=(time.perf_counter() - start) * 1000,
                error=f"{device_id} exceeded {timeout_ms:.1f}ms budget",
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.warning("Guarded device %s failed: %s", device_id, exc, exc_info=True)
            return DeviceExecutionResult(
                device_id=device_id,
                ok=False,
                status="fault",
                latency_ms=(time.perf_counter() - start) * 1000,
                error=str(exc),
                metadata=metadata or {},
            )

    async def _invoke(self, operation: Callable[[], Any]) -> Any:
        result = await asyncio.to_thread(operation)
        if inspect.isawaitable(result):
            return await result
        return result

class FaultGuard:
    """
    Fault Containment and Quota Monitoring.
    Implements §6 of the AIVM ↔ NPC Contract.
    """

    @staticmethod
    def contain(npc: NPC):
        """
        Decorator/Wrapper to contain NPC tick execution.
        Ensures that failures and quota violations do not crash the host.
        """
        def decorator(func: Callable):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    # TODO: Implement more granular quota checks (memory, tokens)
                    result = await func(*args, **kwargs)
                    
                    # Latency check
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    if duration_ms > npc.resource_quota.latency_ceiling_ms:
                        npc.add_audit("quota_violation", {
                            "type": "latency", 
                            "limit": npc.resource_quota.latency_ceiling_ms,
                            "actual": duration_ms
                        })
                        logger.warning(f"NPC {npc.identity.id} exceeded latency ceiling: {duration_ms:.2f}ms")
                    
                    return result

                except Exception as e:
                    logger.error(f"Fault detected in NPC {npc.identity.id}: {e}", exc_info=True)
                    npc.add_audit("fault", {"error": str(e)})
                    
                    # Return SafeDefaultBehavior as defined in §9
                    return {
                        "response": "... (The character seems lost in thought) ...",
                        "status": "degraded",
                        "error": str(e)
                    }
            return wrapper
        return decorator
