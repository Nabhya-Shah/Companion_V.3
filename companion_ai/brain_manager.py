"""Compatibility alias for legacy brain_manager import path.

This module path resolves to companion_ai.brain.manager to preserve import and
patch behavior for older code paths.
"""

import sys as _sys

from companion_ai.brain import manager as _manager_module

_sys.modules[__name__] = _manager_module
