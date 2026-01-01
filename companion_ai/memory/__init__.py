# companion_ai/memory/__init__.py
"""Memory subsystem - all memory backends and utilities."""

# Mem0 backend - the primary memory system
from companion_ai.memory.mem0_backend import (
    get_memory,
    add_memory,
    search_memories,
    get_all_memories,
    delete_memory,
    clear_all_memories,
    build_memory_context,
    get_memory_stats,
    memory_search_tool,
    MemoryStats,
    MemoryContext,
)

# Re-export with aliases for compatibility
get_memory_context = build_memory_context

__all__ = [
    # Mem0 backend
    'get_memory', 'add_memory', 'search_memories', 'get_all_memories',
    'delete_memory', 'clear_all_memories', 'build_memory_context',
    'get_memory_context', 'get_memory_stats', 'memory_search_tool',
    'MemoryStats', 'MemoryContext',
]
