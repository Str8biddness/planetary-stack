"""Compatibility package for legacy ``core.generation.*`` imports."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
__path__ = [str(_ROOT / "packages" / "reasoning" / "generation")]

