from __future__ import annotations
import json
import hashlib
from typing import List, Any, Optional
from .base import Device

class VMD(Device):
    """
    Virtual Memory Device - §3.2
    Wraps existing MemoryStore with contract compliance.
    """
    
    def __init__(self, character_id: str, store: Any):
        self._character_id = character_id
        self._store = store
        self._quota_bytes = 10 * 1024 * 1024 # 10MB
        self._local_events: List[dict[str, Any]] = []

    def write(self, content: str, memory_type: str = "working", importance: float = 0.5) -> str:
        if self._store is None:
            ref = f"{self._character_id}:local:{len(self._local_events)}"
            self._local_events.append({
                "ref": ref,
                "content": content,
                "memory_type": memory_type,
                "importance": importance,
            })
            return ref

        return self._store.store(
            character_id=self._character_id,
            content=content,
            memory_type=memory_type,
            importance=importance
        )

    def recall(self, query: str, k: int = 5) -> List[Any]:
        if self._store is None:
            if not query:
                return self._local_events[-k:]
            needle = query.lower()
            return [
                event for event in self._local_events
                if needle in str(event.get("content", "")).lower()
            ][-k:]

        return self._store.recall(self._character_id, query, top_k=k)

    def snapshot(self) -> bytes:
        return json.dumps({
            "character_id": self._character_id,
            "local_events": self._local_events,
        }, sort_keys=True).encode()

    def restore(self, blob: bytes) -> None:
        data = json.loads(blob.decode())
        if isinstance(data, str):
            self._character_id = data
            self._local_events = []
            return
        self._character_id = data["character_id"]
        self._local_events = list(data.get("local_events", []))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
