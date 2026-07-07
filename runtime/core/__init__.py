"""Compatibility package for legacy ``core.*`` imports.

Synthesus 4.0 source lives under ``packages/``. This shim preserves the public
``core`` import path used by existing tests and downstream integrations.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
__path__ = [
    str(_ROOT / "packages" / "core"),
    str(_ROOT / "packages" / "knowledge"),
    str(Path(__file__).resolve().parent),
]
