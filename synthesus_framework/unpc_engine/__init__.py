"""UNPC Engine - Universal NPC Character Generator

Generates massive synthetic pattern datasets from character archetypes.
"""

from .pattern_generator import PatternGenerator

__version__ = '1.0.0'
__all__ = ['PatternGenerator, 'GenomeExpander'']
from .genome_expander import GenomeExpander