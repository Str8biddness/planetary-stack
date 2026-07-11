"""SW-4 — Adapter load + base-compat validation.

Adapters are DATA (manifest JSON / weight files), never executable code.
A missing or incompatible adapter must fail loud — no silent fake persona.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

# Forbidden executable / script suffixes — adapters are data only.
_FORBIDDEN_SUFFIXES = frozenset(
    {".py", ".sh", ".bash", ".exe", ".so", ".dll", ".bat", ".ps1", ".js"}
)


@dataclass(frozen=True)
class AdapterManifest:
    """Declarative adapter metadata (data plane)."""

    adapter_id: str
    base_model: str
    kind: str = "persona_delta"  # persona_delta | lora
    path: str | None = None
    weight_files: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, default_path: str | None = None) -> "AdapterManifest":
        weights = data.get("weight_files") or data.get("files") or []
        if isinstance(weights, str):
            weights = [weights]
        return cls(
            adapter_id=str(data.get("adapter_id") or data.get("id") or Path(default_path or "adapter").stem),
            base_model=str(data.get("base_model") or data.get("base") or ""),
            kind=str(data.get("kind") or "persona_delta"),
            path=default_path,
            weight_files=tuple(str(w) for w in weights),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class AdapterValidation:
    ok: bool
    reason: str
    manifest: AdapterManifest | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "manifest": None
            if self.manifest is None
            else {
                "adapter_id": self.manifest.adapter_id,
                "base_model": self.manifest.base_model,
                "kind": self.manifest.kind,
                "path": self.manifest.path,
                "weight_files": list(self.manifest.weight_files),
            },
            "details": dict(self.details),
        }


class AdapterLoader:
    """Validate and describe adapters without executing them."""

    def __init__(self, *, expected_base_model: str, root: str | Path | None = None) -> None:
        self.expected_base_model = expected_base_model
        self.root = Path(root) if root else None

    def resolve_path(self, adapter_ref: str) -> Path:
        p = Path(adapter_ref)
        if not p.is_absolute() and self.root is not None:
            p = self.root / p
        return p

    def load_manifest(self, adapter_ref: str) -> AdapterManifest:
        path = self.resolve_path(adapter_ref)
        if not path.exists():
            raise FileNotFoundError(f"adapter not found: {path}")
        if path.suffix.lower() in _FORBIDDEN_SUFFIXES:
            raise ValueError(
                f"adapter ref looks executable ({path.suffix}); adapters must be DATA only"
            )
        if path.is_dir():
            manifest_path = path / "adapter.json"
            if not manifest_path.is_file():
                # Directory of weight files — synthesize manifest
                weights = tuple(
                    str(f.name)
                    for f in sorted(path.iterdir())
                    if f.is_file() and f.suffix.lower() not in _FORBIDDEN_SUFFIXES
                )
                return AdapterManifest(
                    adapter_id=path.name,
                    base_model=self.expected_base_model,
                    kind="lora",
                    path=str(path),
                    weight_files=weights,
                    notes="directory adapter without adapter.json",
                )
            path = manifest_path
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                raise ValueError("adapter.json must be an object")
            return AdapterManifest.from_dict(data, default_path=str(path))
        # Single weight file
        if path.suffix.lower() in _FORBIDDEN_SUFFIXES:
            raise ValueError(f"refused executable adapter path: {path}")
        return AdapterManifest(
            adapter_id=path.stem,
            base_model=self.expected_base_model,
            kind="lora",
            path=str(path),
            weight_files=(path.name,),
        )

    def validate(
        self,
        adapter_ref: str | None,
        *,
        require_exists: bool = True,
    ) -> AdapterValidation:
        if not adapter_ref:
            return AdapterValidation(ok=True, reason="no_adapter", manifest=None)

        path = self.resolve_path(adapter_ref)
        if require_exists and not path.exists():
            logger.warning("adapter MISSING: %s", path)
            return AdapterValidation(
                ok=False,
                reason="adapter_missing",
                details={"path": str(path)},
            )

        try:
            if path.suffix.lower() in _FORBIDDEN_SUFFIXES:
                return AdapterValidation(
                    ok=False,
                    reason="adapter_executable_forbidden",
                    details={"path": str(path), "suffix": path.suffix},
                )
            manifest = self.load_manifest(adapter_ref)
        except FileNotFoundError as e:
            return AdapterValidation(ok=False, reason="adapter_missing", details={"error": str(e)})
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning("adapter invalid: %s (%s)", adapter_ref, e)
            return AdapterValidation(
                ok=False,
                reason="adapter_invalid",
                details={"error": str(e), "path": str(path)},
            )

        if manifest.base_model and self.expected_base_model:
            # Compat: exact match or base is prefix of expected (e.g. llama3.2 vs llama3.2:3b)
            base = manifest.base_model.strip()
            expected = self.expected_base_model.strip()
            if base and expected and base != expected and not expected.startswith(base) and not base.startswith(expected.split(":")[0]):
                return AdapterValidation(
                    ok=False,
                    reason="base_model_mismatch",
                    manifest=manifest,
                    details={"adapter_base": base, "expected_base": expected},
                )

        for wf in manifest.weight_files:
            wp = Path(wf)
            if not wp.is_absolute() and manifest.path:
                parent = Path(manifest.path)
                if parent.is_file():
                    parent = parent.parent
                wp = parent / wf
            if wp.suffix.lower() in _FORBIDDEN_SUFFIXES:
                return AdapterValidation(
                    ok=False,
                    reason="adapter_executable_forbidden",
                    manifest=manifest,
                    details={"weight": str(wp)},
                )

        return AdapterValidation(ok=True, reason="ok", manifest=manifest)

    def describe_for_prompt(self, adapter_ref: str | None) -> str:
        """Return a non-executing description string for logging / telemetry."""
        v = self.validate(adapter_ref)
        if not v.ok:
            return f"DEGRADED:{v.reason}"
        if v.manifest is None:
            return "none"
        return f"{v.manifest.kind}:{v.manifest.adapter_id}:base={v.manifest.base_model}"
