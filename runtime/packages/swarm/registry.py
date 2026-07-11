"""SW-1 — Expert registry (deltas only, never model copies).

Each expert is a cheap delta over a shared base model:
  persona + system_prompt + retrieval namespace + optional adapter_ref (data).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Expert:
    """One persona-clone expert — a delta, not a model copy."""

    expert_id: str
    persona: str
    system_prompt: str
    namespace: str
    domain: str = "general"
    adapter_ref: str | None = None  # path / id of LoRA or persona-delta DATA only

    def __post_init__(self) -> None:
        if not str(self.expert_id).strip():
            raise ValueError("expert_id is required")
        if not str(self.system_prompt).strip():
            raise ValueError("system_prompt is required (cheap delta; no empty persona)")
        if not str(self.namespace).strip():
            raise ValueError("namespace is required for retrieval isolation of grounding")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Expert":
        return cls(
            expert_id=str(data["expert_id"]),
            persona=str(data.get("persona") or data["expert_id"]),
            system_prompt=str(data["system_prompt"]),
            namespace=str(data["namespace"]),
            domain=str(data.get("domain") or "general"),
            adapter_ref=(
                str(data["adapter_ref"])
                if data.get("adapter_ref") not in (None, "")
                else None
            ),
        )


@dataclass
class SwarmRequest:
    query: str
    expert_ids: list[str]
    budget: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.query).strip():
            raise ValueError("SwarmRequest.query is required")
        if not self.expert_ids:
            raise ValueError("SwarmRequest.expert_ids must be non-empty")


@dataclass
class ExpertResult:
    expert_id: str
    text: str
    confidence: float
    provenance_refs: list[str] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: str | None = None
    persona: str | None = None
    namespace: str | None = None
    latency_ms: float = 0.0
    model_id: str | None = None  # always the shared base when healthy
    sources: list[dict[str, Any]] = field(default_factory=list)
    # v1 honesty: LoRA/weight adapters are validated as DATA only — never hot-swapped.
    # Behavioral delta today = system_prompt + namespace (see adapters/loader.py).
    adapter_applied: bool = False
    adapter_status: str | None = None  # none | validated_not_applied | missing | …

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SwarmAnswer:
    response: str
    contributing_experts: list[str]
    arbitration: dict[str, Any]
    sources: list[dict[str, Any]] = field(default_factory=list)
    expert_results: list[dict[str, Any]] = field(default_factory=list)
    degraded_experts: list[str] = field(default_factory=list)
    model_id: str | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExpertRegistry:
    """In-memory expert registry. Stores deltas only — never model weights."""

    def __init__(self) -> None:
        self._experts: dict[str, Expert] = {}

    def register(self, expert: Expert) -> None:
        if expert.expert_id in self._experts:
            logger.info("registry: replacing expert %s", expert.expert_id)
        self._experts[expert.expert_id] = expert

    def unregister(self, expert_id: str) -> bool:
        return self._experts.pop(expert_id, None) is not None

    def get(self, expert_id: str) -> Expert | None:
        return self._experts.get(expert_id)

    def require(self, expert_id: str) -> Expert:
        exp = self.get(expert_id)
        if exp is None:
            raise KeyError(f"expert not registered: {expert_id}")
        return exp

    def list_ids(self) -> list[str]:
        return sorted(self._experts.keys())

    def __iter__(self) -> Iterator[Expert]:
        return iter(self._experts.values())

    def __len__(self) -> int:
        return len(self._experts)

    def load_json(self, path: str | Path) -> int:
        """Load experts from a JSON list or {experts: [...]}. Returns count added."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"expert registry file not found: {p}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        items: Iterable[Mapping[str, Any]]
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict) and isinstance(raw.get("experts"), list):
            items = raw["experts"]
        else:
            raise ValueError("registry JSON must be a list or {experts: [...]}")
        n = 0
        for row in items:
            if not isinstance(row, Mapping):
                continue
            self.register(Expert.from_dict(row))
            n += 1
        return n

    def snapshot(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._experts.values()]
