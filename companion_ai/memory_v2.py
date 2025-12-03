"""Memory V2 - Mem0 Integration with Groq Backend.

Provides a hybrid memory system that:
1. Auto-retrieves relevant memories for context
2. Shows memory stats so 120B knows what's available
3. Provides memory_search tool for deep digs
4. Stores new facts from conversations

Uses Groq as LLM backend (no extra API key needed).
"""
from __future__ import annotations
import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy import - only load Mem0 when actually used
_memory_instance = None


@dataclass
class MemoryStats:
    """Statistics about the user's memory."""
    total_memories: int
    categories: Dict[str, int]  # category -> count


@dataclass  
class MemoryContext:
    """Context to inject into prompts."""
    stats: MemoryStats
    relevant_memories: List[str]
    has_memories: bool


def _get_mem0_config() -> dict:
    """Build Mem0 configuration with Groq backend and local embeddings."""
    from companion_ai.core import config as core_config
    import os
    
    # Use a dedicated path in the data folder for Qdrant storage
    qdrant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mem0_qdrant")
    
    return {
        "llm": {
            "provider": "groq",
            "config": {
                "model": "llama-3.1-8b-instant",
                "temperature": 0.1,
                "max_tokens": 1000,
                "api_key": core_config.GROQ_API_KEY,
            }
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_dims": 384,  # MiniLM outputs 384 dimensions
            }
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "companion_memories",
                "path": qdrant_path,
                "embedding_model_dims": 384,  # Must match embedder!
                "on_disk": True,  # Enable persistent storage!
            }
        },
        "version": "v1.1",
    }


def get_memory() -> Any:
    """Get or create the Mem0 memory instance."""
    global _memory_instance
    
    if _memory_instance is None:
        try:
            from mem0 import Memory
            config = _get_mem0_config()
            logger.info(f"🧠 Creating NEW Mem0 instance with config: {config}")
            _memory_instance = Memory.from_config(config)
            logger.info("✅ Mem0 initialized with Groq backend")
        except ImportError:
            logger.error("Mem0 not installed. Run: pip install mem0ai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Mem0: {e}")
            raise
    else:
        logger.info("🔄 Reusing existing Mem0 instance")
    
    return _memory_instance


def add_memory(
    messages: List[Dict[str, str]],
    user_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Add memories from a conversation.
    
    Args:
        messages: List of {"role": "user/assistant", "content": "..."}
        user_id: User identifier
        metadata: Optional metadata tags
        
    Returns:
        Result from Mem0
    """
    try:
        memory = get_memory()
        result = memory.add(messages, user_id=user_id, metadata=metadata or {})
        logger.info(f"📝 Added memories for user {user_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        return {"error": str(e)}


def search_memories(
    query: str,
    user_id: str = "default",
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Search for relevant memories.
    
    Args:
        query: Search query
        user_id: User identifier
        limit: Max results
        
    Returns:
        List of memory results
    """
    try:
        memory = get_memory()
        response = memory.search(query, user_id=user_id, limit=limit)
        # Mem0 returns {'results': [...]}
        results = response.get('results', []) if isinstance(response, dict) else response
        logger.info(f"🔍 Found {len(results)} memories for query: {query[:50]}")
        return results
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        return []


def get_all_memories(user_id: str = "default") -> List[Dict[str, Any]]:
    """Get all memories for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        List of all memories
    """
    try:
        memory = get_memory()
        response = memory.get_all(user_id=user_id)
        # Mem0 returns {'results': [...]}
        results = response.get('results', []) if isinstance(response, dict) else response
        return results
    except Exception as e:
        logger.error(f"Failed to get all memories: {e}")
        return []


def get_memory_stats(user_id: str = "default") -> MemoryStats:
    """Get statistics about user's memories.
    
    Args:
        user_id: User identifier
        
    Returns:
        MemoryStats with counts
    """
    try:
        memories = get_all_memories(user_id)
        
        # Count by category from metadata (metadata can be None)
        categories: Dict[str, int] = {}
        for mem in memories:
            metadata = mem.get("metadata") or {}
            cat = metadata.get("category", "general") if isinstance(metadata, dict) else "general"
            categories[cat] = categories.get(cat, 0) + 1
        
        return MemoryStats(
            total_memories=len(memories),
            categories=categories
        )
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return MemoryStats(total_memories=0, categories={})


def build_memory_context(
    user_message: str,
    user_id: str = "default",
    max_relevant: int = 3
) -> MemoryContext:
    """Build memory context for a user message.
    
    This is the main function used by context_builder to inject
    memory awareness into prompts.
    
    Args:
        user_message: The current user message
        user_id: User identifier
        max_relevant: Max relevant memories to include
        
    Returns:
        MemoryContext with stats and relevant memories
    """
    try:
        # Get stats
        stats = get_memory_stats(user_id)
        
        # Search for relevant memories
        relevant = []
        if stats.total_memories > 0:
            results = search_memories(user_message, user_id, limit=max_relevant)
            relevant = [r.get("memory", r.get("text", str(r))) for r in results]
        
        return MemoryContext(
            stats=stats,
            relevant_memories=relevant,
            has_memories=stats.total_memories > 0
        )
    except Exception as e:
        logger.error(f"Failed to build memory context: {e}")
        return MemoryContext(
            stats=MemoryStats(total_memories=0, categories={}),
            relevant_memories=[],
            has_memories=False
        )


def format_memory_for_prompt(context: MemoryContext) -> str:
    """Format memory context for injection into system prompt.
    
    Args:
        context: MemoryContext from build_memory_context
        
    Returns:
        Formatted string for prompt
    """
    if not context.has_memories:
        return "[YOUR MEMORY]\nNo memories stored yet."
    
    lines = ["[YOUR MEMORY]"]
    lines.append(f"Total facts: {context.stats.total_memories}")
    
    if context.stats.categories:
        cats = ", ".join([f"{k} ({v})" for k, v in context.stats.categories.items()])
        lines.append(f"Categories: {cats}")
    
    if context.relevant_memories:
        lines.append("")
        lines.append("[AUTO-RETRIEVED]")
        for mem in context.relevant_memories:
            lines.append(f"• {mem}")
    
    lines.append("")
    lines.append("[Use memory_search(topic) for more]")
    
    return "\n".join(lines)


def delete_memory(memory_id: str) -> bool:
    """Delete a specific memory.
    
    Args:
        memory_id: The memory ID to delete
        
    Returns:
        True if successful
    """
    try:
        memory = get_memory()
        memory.delete(memory_id)
        logger.info(f"🗑️ Deleted memory: {memory_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        return False


def clear_all_memories(user_id: str = "default") -> bool:
    """Clear all memories for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        True if successful
    """
    try:
        memory = get_memory()
        memory.delete_all(user_id=user_id)
        logger.info(f"🗑️ Cleared all memories for user: {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to clear memories: {e}")
        return False


# Tool function for 120B to use
def memory_search_tool(query: str, user_id: str = "default") -> str:
    """Tool function for searching memories.
    
    This is exposed as a tool for the LLM to use when it needs
    to dig deeper into memory beyond auto-retrieved context.
    
    Args:
        query: What to search for
        user_id: User identifier
        
    Returns:
        Formatted search results
    """
    results = search_memories(query, user_id, limit=5)
    
    if not results:
        return f"No memories found for: {query}"
    
    lines = [f"🔍 Memory Search: '{query}'", ""]
    for i, r in enumerate(results, 1):
        mem = r.get("memory", r.get("text", str(r)))
        score = r.get("score", 0)
        lines.append(f"{i}. {mem} (relevance: {score:.2f})")
    
    return "\n".join(lines)
