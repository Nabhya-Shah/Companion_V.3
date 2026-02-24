"""Compatibility wrapper for legacy Memory V2 imports."""

from companion_ai.memory.mem0_backend import (
    MemoryStats,
    MemoryContext,
    add_memory,
    search_memories,
    get_all_memories,
    get_memory_stats,
    build_memory_context,
    format_memory_for_prompt,
    delete_memory,
    update_memory,
    clear_all_memories,
    memory_search_tool,
)

__all__ = [
    "MemoryStats",
    "MemoryContext",
    "add_memory",
    "search_memories",
    "get_all_memories",
    "get_memory_stats",
    "build_memory_context",
    "format_memory_for_prompt",
    "delete_memory",
    "update_memory",
    "clear_all_memories",
    "memory_search_tool",
]
