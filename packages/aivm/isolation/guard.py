from __future__ import annotations
import logging
import functools
import time
from typing import Any, Callable, Dict, Optional
from ..kernel.npc import NPC

logger = logging.getLogger("aivm.isolation")

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
