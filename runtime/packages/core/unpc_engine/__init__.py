"""UNPC Engine - Universal NPC Character Generator.

Generates massive synthetic pattern datasets from character archetypes.
"""

from __future__ import annotations

try:
    from pattern_generator import PatternGenerator
except ImportError:  # package-relative
    try:
        from .pattern_generator import PatternGenerator  # type: ignore
    except ImportError:
        PatternGenerator = None  # type: ignore

try:
    from genome_expander import GenomeExpander
except ImportError:
    try:
        from .genome_expander import GenomeExpander  # type: ignore
    except ImportError:
        GenomeExpander = None  # type: ignore

__version__ = "1.0.0"
__all__ = ["PatternGenerator", "GenomeExpander"]
