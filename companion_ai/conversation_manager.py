"""Compatibility alias for legacy conversation_manager import path.

This module path resolves to companion_ai.runtime.conversation so monkeypatches
on companion_ai.conversation_manager continue to affect canonical behavior.
"""

import sys as _sys

from companion_ai.runtime import conversation as _conversation_module

_sys.modules[__name__] = _conversation_module
