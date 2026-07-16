"""Compatibility alias for the Knowledge Cloud implementation.

The implementation lives in :mod:`knowledge.knowledge_cloud`, while older
runtime components and public imports still use ``core.knowledge_cloud``.
Alias the module itself so monkeypatches and module-level state are shared.
"""

import sys

from knowledge import knowledge_cloud as _implementation

sys.modules[__name__] = _implementation
