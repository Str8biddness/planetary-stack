"""Compatibility alias for the Knowledge Cloud RAG pipeline."""

import sys

from knowledge import rag_pipeline as _implementation

sys.modules[__name__] = _implementation
