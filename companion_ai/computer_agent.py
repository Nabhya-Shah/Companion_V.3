"""Compatibility alias for legacy computer_agent import path.

This module path resolves to companion_ai.runtime.computer so monkeypatches on
companion_ai.computer_agent continue to affect canonical behavior.
"""

import sys as _sys

from companion_ai.runtime import computer as _computer_module

_sys.modules[__name__] = _computer_module
