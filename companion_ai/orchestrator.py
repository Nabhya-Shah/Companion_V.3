"""Compatibility alias for legacy orchestrator import path.

This module path resolves to companion_ai.runtime.orchestrator so monkeypatches
on companion_ai.orchestrator continue to affect canonical behavior.
"""

import sys as _sys

from companion_ai.runtime import orchestrator as _orchestrator_module

_sys.modules[__name__] = _orchestrator_module
