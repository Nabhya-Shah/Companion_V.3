"""Compatibility wrapper for legacy memory graph imports."""

from companion_ai.memory.knowledge_graph import (
    clear_graph,
    search_graph,
    get_graph_stats,
    export_graph,
    build_semantic_graph_from_memories,
)

__all__ = [
    "clear_graph",
    "search_graph",
    "get_graph_stats",
    "export_graph",
    "build_semantic_graph_from_memories",
]
