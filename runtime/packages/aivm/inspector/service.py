from __future__ import annotations
import asyncio
import json
import logging
from typing import Dict, List, Set, Any
from fastapi import WebSocket

logger = logging.getLogger("aivm.inspector")

class InspectorService:
    """
    Real-time visibility into the AIVM Kernel.
    Streams NPC audit entries to connected observers via WebSockets.
    """

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {} # npc_id -> sockets
        self._global_observers: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, npc_id: Optional[str] = None):
        await websocket.accept()
        if npc_id:
            if npc_id not in self._connections:
                self._connections[npc_id] = set()
            self._connections[npc_id].add(websocket)
        else:
            self._global_observers.add(websocket)
        logger.info(f"Inspector: New connection (NPC={npc_id})")

    def disconnect(self, websocket: WebSocket, npc_id: Optional[str] = None):
        if npc_id and npc_id in self._connections:
            self._connections[npc_id].discard(websocket)
        else:
            self._global_observers.discard(websocket)

    async def broadcast_event(self, npc_id: str, step: str, details: Dict[str, Any]):
        """Broadcast a cognitive trace event to all interested observers."""
        payload = {
            "type": "trace_event",
            "npc_id": npc_id,
            "step": step,
            "details": details,
            "timestamp": details.get("timestamp", "") # Should be in details if using NPC.add_audit
        }
        
        message = json.dumps(payload)
        
        # 1. Targeted observers
        if npc_id in self._connections:
            for socket in list(self._connections[npc_id]):
                try:
                    await socket.send_text(message)
                except Exception:
                    self._connections[npc_id].discard(socket)

        # 2. Global observers
        for socket in list(self._global_observers):
            try:
                await socket.send_text(message)
            except Exception:
                self._global_observers.discard(socket)

# Global singleton for the AIOS server
_inspector = InspectorService()

def get_inspector() -> InspectorService:
    return _inspector
