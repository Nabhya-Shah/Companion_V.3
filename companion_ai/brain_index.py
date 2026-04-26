"""Compatibility alias for legacy brain_index import path.

This module path resolves to companion_ai.brain.index so monkeypatches on
companion_ai.brain_index (for tests/tools) affect the canonical module.
"""

import sys as _sys

from companion_ai.brain import index as _index_module

_sys.modules[__name__] = _index_module
