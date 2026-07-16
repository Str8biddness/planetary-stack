"""Compatibility alias for :mod:`reasoning.reasoning_core`."""

import sys

from reasoning import reasoning_core as _implementation

sys.modules[__name__] = _implementation
