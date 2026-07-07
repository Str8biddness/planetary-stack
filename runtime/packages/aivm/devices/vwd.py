from __future__ import annotations

import hashlib
import json
from typing import Any

from .base import Device


class VWD(Device):
    """
    Virtual Writeback Device.
    Stages validated trace/memory commits before durable backend admission.
    """

    def __init__(self, owner_id: str):
        self._owner_id = owner_id
        self._records: list[dict[str, Any]] = []

    def stage(self, content: Any, *, target: str = "episodic", provenance: str | None = None) -> str:
        ref = f"{self._owner_id}:writeback:{len(self._records)}"
        self._records.append({
            "ref": ref,
            "target": target,
            "provenance": provenance,
            "content": content,
        })
        return ref

    def pending(self) -> list[dict[str, Any]]:
        return list(self._records)

    def snapshot(self) -> bytes:
        return json.dumps({
            "owner_id": self._owner_id,
            "records": self._records,
        }, sort_keys=True).encode()

    def restore(self, blob: bytes) -> None:
        data = json.loads(blob.decode())
        self._owner_id = data["owner_id"]
        self._records = list(data.get("records", []))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
