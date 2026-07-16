"""Compatibility alias for the Knowledge-plane memory store."""

import sys

from knowledge import memory_store as _implementation

sys.modules[__name__] = _implementation
