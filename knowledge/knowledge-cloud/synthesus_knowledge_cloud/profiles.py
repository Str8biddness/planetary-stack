"""Dataset profile loading for bounded Knowledge Cloud builds."""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - fallback documented by CLI error
    yaml = None


def load_profile(path: str | Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load profile YAML files")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def summarize_profile(profile: dict) -> str:
    sources = profile.get("sources", [])
    outputs = profile.get("outputs", {})
    return (
        f"profile={profile.get('name', 'unknown')} "
        f"sources={len(sources)} "
        f"max_entries={profile.get('limits', {}).get('max_entries', 'unbounded')} "
        f"outputs={','.join(k for k, enabled in outputs.items() if enabled)}"
    )
