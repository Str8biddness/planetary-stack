"""Archetype Loader - Loads and validates NPC archetype JSON definitions"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

ARCHETYPES_DIR = Path(__file__).parent / "archetypes"

_CACHE: Dict[str, Dict[str, Any]] = {}


def load_archetype(archetype_name: str) -> Optional[Dict[str, Any]]:
    """Load an archetype from the JSON definitions directory."""
    if archetype_name in _CACHE:
        return _CACHE[archetype_name]
    path = ARCHETYPES_DIR / f"{archetype_name}.json"
    if not path.exists():
        logger.warning(f"Archetype not found: {archetype_name} at {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _validate_archetype(data)
        _CACHE[archetype_name] = data
        logger.debug(f"Loaded archetype: {archetype_name}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in {archetype_name}: {e}")
        return None
    except ValueError as e:
        logger.error(f"Invalid archetype {archetype_name}: {e}")
        return None


def list_archetypes() -> List[str]:
    """Return a list of all available archetype names."""
    if not ARCHETYPES_DIR.exists():
        return []
    return [
        p.stem for p in ARCHETYPES_DIR.glob("*.json")
        if p.is_file()
    ]


def load_all_archetypes() -> Dict[str, Dict[str, Any]]:
    """Load all available archetypes into cache."""
    results = {}
    for name in list_archetypes():
        data = load_archetype(name)
        if data:
            results[name] = data
    logger.info(f"Loaded {len(results)} archetypes from {ARCHETYPES_DIR}")
    return results


def get_trait_profile(archetype_name: str) -> Dict[str, float]:
    """Get just the trait values for an archetype."""
    arch = load_archetype(archetype_name)
    if not arch:
        return {}
    return arch.get("traits", {})


def get_speech_patterns(archetype_name: str) -> List[str]:
    """Get the speech patterns for an archetype."""
    arch = load_archetype(archetype_name)
    if not arch:
        return []
    return arch.get("speech_patterns", [])


def _validate_archetype(data: Dict[str, Any]) -> None:
    """Validate that an archetype has required fields."""
    required = ["archetype", "traits", "response_style"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    traits = data.get("traits", {})
    for trait, val in traits.items():
        if not isinstance(val, (int, float)) or not (0.0 <= val <= 1.0):
            raise ValueError(f"Trait '{trait}' must be a float between 0.0 and 1.0")


def clear_cache():
    """Clear the archetype cache."""
    _CACHE.clear()
    logger.debug("Archetype cache cleared")
