"""Brain subsystem package.

Canonical modules:
1. companion_ai.brain.index: semantic brain document index.
2. companion_ai.brain.manager: persistent brain file manager.

Legacy compatibility modules remain available at:
1. companion_ai.brain_index
2. companion_ai.brain_manager
"""

from companion_ai.brain.index import BrainIndex
from companion_ai.brain.manager import (
    BrainManager,
    get_brain,
    brain_read,
    brain_write,
    brain_list,
    get_brain_context,
    get_brain_file_map,
)


def get_brain_index():
    """Forward to legacy shim for monkeypatch compatibility in existing tests/tools."""
    import companion_ai.brain_index as legacy_index

    return legacy_index.get_brain_index()


def brain_search(query: str, limit: int = 3):
    """Forward to legacy shim so patched legacy module behavior is preserved."""
    import companion_ai.brain_index as legacy_index

    return legacy_index.brain_search(query, limit)


def start_background_indexing():
    """Forward to legacy shim so startup hooks keep a single compatibility path."""
    import companion_ai.brain_index as legacy_index

    return legacy_index.start_background_indexing()

__all__ = [
    "BrainIndex",
    "get_brain_index",
    "brain_search",
    "start_background_indexing",
    "BrainManager",
    "get_brain",
    "brain_read",
    "brain_write",
    "brain_list",
    "get_brain_context",
    "get_brain_file_map",
]
