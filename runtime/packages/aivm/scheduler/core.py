from __future__ import annotations
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Awaitable
from ..kernel.types import SchedulerClass, ResourceQuota

logger = logging.getLogger("aivm.scheduler")

@dataclass
class ScheduledTask:
    npc_id: str
    payload: Dict[str, Any]
    priority: int
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default_factory=asyncio.Future)

class AIVMScheduler:
    """
    Multi-NPC Execution Scheduler.
    Implements §8 of the AIVM ↔ NPC Contract.
    Manages priorities, quotas, and prevents compute starvation.
    """

    def __init__(self, kernel: Any, concurrency_limit: int = 5):
        self._kernel = kernel
        self._concurrency_limit = concurrency_limit
        self._queues: Dict[SchedulerClass, deque[ScheduledTask]] = {
            sc: deque() for sc in SchedulerClass
        }
        self._running_count = 0
        self._is_active = False
        self._worker_task: Optional[asyncio.Task] = None

    def start(self):
        if not self._is_active:
            self._is_active = True
            self._worker_task = asyncio.create_task(self._scheduler_loop())
            logger.info(f"AIVM Scheduler started (concurrency={self._concurrency_limit})")

    def stop(self):
        self._is_active = False
        if self._worker_task:
            self._worker_task.cancel()
            logger.info("AIVM Scheduler stopped")

    async def schedule_tick(self, npc_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add a tick request to the priority queue and await result."""
        npc = self._kernel._npcs.get(npc_id)
        if not npc:
            raise ValueError(f"NPC {npc_id} not found in kernel.")

        task = ScheduledTask(
            npc_id=npc_id,
            payload=payload,
            priority=self._get_priority(npc.scheduler_class)
        )
        
        self._queues[npc.scheduler_class].append(task)
        return await task.future

    def _get_priority(self, sc: SchedulerClass) -> int:
        priorities = {
            SchedulerClass.REALTIME_PRINCIPAL: 0,
            SchedulerClass.REALTIME_SUPPORTING: 1,
            SchedulerClass.AMBIENT: 2,
            SchedulerClass.OFFLINE: 3
        }
        return priorities.get(sc, 99)

    async def _scheduler_loop(self):
        while self._is_active:
            if self._running_count < self._concurrency_limit:
                task = self._pick_next_task()
                if task:
                    self._running_count += 1
                    asyncio.create_task(self._execute_task(task))
                else:
                    await asyncio.sleep(0.01) # Idle
            else:
                await asyncio.sleep(0.01) # At capacity

    def _pick_next_task(self) -> Optional[ScheduledTask]:
        # Strict priority ordering: Principal -> Supporting -> Ambient -> Offline
        for sc in [
            SchedulerClass.REALTIME_PRINCIPAL,
            SchedulerClass.REALTIME_SUPPORTING,
            SchedulerClass.AMBIENT,
            SchedulerClass.OFFLINE
        ]:
            if self._queues[sc]:
                return self._queues[sc].popleft()
        return None

    async def _execute_task(self, task: ScheduledTask):
        try:
            # Enforce Quota and execute tick via Kernel
            result = await self._kernel.tick(task.npc_id, task.payload)
            task.future.set_result(result)
        except Exception as e:
            task.future.set_exception(e)
        finally:
            self._running_count -= 1
