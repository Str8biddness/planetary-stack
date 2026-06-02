from __future__ import annotations
import hashlib
import json
from typing import List, Any, Optional
from .base import Device

class VQD(Device):
    """
    Virtual Knowledge Device - §3.3
    Wraps existing KnowledgeCloud with contract compliance.
    """
    
    def __init__(self, cloud: Any, scope: Optional[List[str]] = None, policy: Optional[dict[str, Any]] = None):
        self._cloud = cloud
        self._scope = list(scope or ["global"])
        self._policy = {
            "pruning": "bounded",
            "chain_length": 1,
            "gating": "scoped",
            **(policy or {}),
        }
        self._lookup_count = 0
        self._last_lookup: dict[str, Any] | None = None
        self._last_error: str | None = None

    def scope(self) -> List[str]:
        return list(self._scope)

    def set_scope(self, scope: List[str]) -> None:
        self._scope = list(scope)

    def policy(self) -> dict[str, Any]:
        return dict(self._policy)

    def set_policy(self, policy: dict[str, Any]) -> None:
        self._policy = dict(policy)

    def lookup_count(self) -> int:
        return self._lookup_count

    def last_lookup(self) -> dict[str, Any] | None:
        return dict(self._last_lookup) if self._last_lookup is not None else None

    def lookup(self, query: str, limit: int = 5) -> List[Any]:
        bounded_limit = max(0, int(limit))
        self._lookup_count += 1
        self._last_error = None

        if self._cloud is None:
            self._last_lookup = {
                "query": query,
                "limit": bounded_limit,
                "hit_count": 0,
                "scope": self.scope(),
                "backend_mounted": False,
                "status": "unmounted",
            }
            return []

        if not hasattr(self._cloud, "search"):
            self._last_error = "backend_missing_search"
            self._last_lookup = {
                "query": query,
                "limit": bounded_limit,
                "hit_count": 0,
                "scope": self.scope(),
                "backend_mounted": True,
                "status": "fault",
            }
            raise TypeError("VQD knowledge cloud backend must expose search(query, top_k=...)")

        results = self._cloud.search(query, top_k=bounded_limit)
        hit_count = len(results) if hasattr(results, "__len__") else 0
        self._last_lookup = {
            "query": query,
            "limit": bounded_limit,
            "hit_count": hit_count,
            "scope": self.scope(),
            "backend_mounted": True,
            "status": "ok",
        }
        return results

    def snapshot(self) -> bytes:
        return json.dumps({
            "scope": self._scope,
            "policy": self._policy,
            "lookup_count": self._lookup_count,
            "last_lookup": self._last_lookup,
            "last_error": self._last_error,
        }, sort_keys=True).encode()

    def restore(self, blob: bytes) -> None:
        if blob == b"vqd_snapshot":
            self._scope = ["global"]
            self._policy = {
                "pruning": "bounded",
                "chain_length": 1,
                "gating": "scoped",
            }
            self._lookup_count = 0
            self._last_lookup = None
            self._last_error = None
            return

        data = json.loads(blob.decode())
        self._scope = list(data.get("scope", ["global"]))
        self._policy = dict(data.get("policy", {
            "pruning": "bounded",
            "chain_length": 1,
            "gating": "scoped",
        }))
        self._lookup_count = int(data.get("lookup_count", 0))
        self._last_lookup = data.get("last_lookup")
        self._last_error = data.get("last_error")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
