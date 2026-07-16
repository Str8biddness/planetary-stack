"""SW-5 — Firecracker MicroVM envelope (HOSTED only).

On a single-GPU local host, MicroVM isolation between cooperating experts is
forbidden: it would waste the shared GPU and reintroduce model-copy isolation.
This module raises a loud NotImplementedError / BLOCK rather than faking a VM.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any


class FirecrackerLocalBlockedError(NotImplementedError):
    """Raised when Firecracker envelope is requested on a single-GPU local host."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            "BLOCKED: Firecracker MicroVM envelope is HOSTED-only. "
            f"{reason} "
            "On a single-GPU local host, experts share ONE resident base model "
            "with cheap deltas (system_prompt / LoRA data / namespace). "
            "Isolation between cooperating experts is forbidden."
        )


@dataclass
class FirecrackerEnvelopeConfig:
    expert_id: str
    rootfs: str | None = None
    kernel: str | None = None
    vcpu_count: int = 1
    mem_mib: int = 512


def is_local_single_gpu_host() -> bool:
    """Heuristic: local if no HOSTED flag and Firecracker binary not required.

    Hosted deployments set SYNTHESUS_SWARM_HOSTED=1 to opt into MicroVM envelopes.
    """
    if os.environ.get("SYNTHESUS_SWARM_HOSTED", "").strip() in {"1", "true", "yes"}:
        return False
    return True


def firecracker_available() -> bool:
    return shutil.which("firecracker") is not None


class FirecrackerEnvelope:
    """MicroVM lifecycle controller — HOSTED only; local = loud BLOCK."""

    def __init__(self, config: FirecrackerEnvelopeConfig) -> None:
        self.config = config
        self._running = False

    def start(self) -> dict[str, Any]:
        if is_local_single_gpu_host():
            raise FirecrackerLocalBlockedError(
                f"local single-GPU host refused envelope for expert={self.config.expert_id!r}; "
                "SYNTHESUS_SWARM_HOSTED is not set."
            )
        if not firecracker_available():
            raise FirecrackerLocalBlockedError(
                "firecracker binary not found on PATH even though HOSTED mode is set."
            )
        # Hosted path is not implemented in this package revision — still honest.
        raise FirecrackerLocalBlockedError(
            "HOSTED Firecracker lifecycle is not implemented in this revision "
            "(no fake MicroVM). Deploy on the hosted control plane when available."
        )

    def stop(self) -> dict[str, Any]:
        if is_local_single_gpu_host():
            raise FirecrackerLocalBlockedError(
                f"local single-GPU host refused stop() for expert={self.config.expert_id!r}."
            )
        self._running = False
        return {"stopped": True, "expert_id": self.config.expert_id}

    @property
    def running(self) -> bool:
        return self._running


def require_hosted_or_block(expert_id: str = "unknown") -> None:
    """Call at envelope entry points — always raises on local hosts."""
    FirecrackerEnvelope(FirecrackerEnvelopeConfig(expert_id=expert_id)).start()
