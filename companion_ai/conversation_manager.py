"""Compatibility alias for legacy conversation_manager import path.

All symbols are re-exported from companion_ai.runtime.conversation for backward compatibility.
"""

import sys as _sys

from companion_ai.runtime.conversation import ConversationSession

_sys.modules[__name__] = _sys.modules.get("companion_ai.runtime.conversation")

__all__ = ["ConversationSession"]