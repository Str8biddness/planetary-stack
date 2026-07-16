from __future__ import annotations

import hashlib
import json
from typing import Any

from .base import Device


class VCD(Device):
    """
    Virtual Cache Device.
    Captures volatile hot-context cache state as an explicit CHAL partition.
    """

    def __init__(self, owner_id: str):
        self._owner_id = owner_id
        self._entries: dict[str, dict[str, Any]] = {}

    def put(self, key: str, value: Any, *, tier: str = "L1", ttl_ms: int | None = None) -> str:
        ref = f"{self._owner_id}:cache:{key}"
        self._entries[key] = {
            "ref": ref,
            "tier": tier,
            "ttl_ms": ttl_ms,
            "value": value,
        }
        return ref

    def get(self, key: str) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry["value"]

    def entries(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)

    def snapshot(self) -> bytes:
        return json.dumps({
            "owner_id": self._owner_id,
            "entries": self._entries,
        }, sort_keys=True).encode()

    def restore(self, blob: bytes) -> None:
        data = json.loads(blob.decode())
        self._owner_id = data["owner_id"]
        self._entries = dict(data.get("entries", {}))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
