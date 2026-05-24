from __future__ import annotations
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

    def write(self, content: str, memory_type: str = "working", importance: float = 0.5) -> str:
        # Mediated through kernel, but here we call the store
        return self._store.store(
            character_id=self._character_id,
            content=content,
            memory_type=memory_type,
            importance=importance
        )

    def recall(self, query: str, k: int = 5) -> List[Any]:
        return self._store.recall(self._character_id, query, top_k=k)

    def snapshot(self) -> bytes:
        # In a real AIVM, this might dump a buffer. 
        # Here we just return the char_id to link back to DB on restore.
        return self._character_id.encode()

    def restore(self, blob: bytes) -> None:
        self._character_id = blob.decode()

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
