"""Compatibility package for legacy ``knowledge_integration.*`` imports.

Synthesus 4.0 keeps the knowledge source layer under ``packages/knowledge``.
This package preserves the older import path used by tests, scripts, and
downstream runtimes.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
__path__ = [str(_ROOT / "packages" / "knowledge")]
