"""Memory V2 - Mem0 Integration with Ollama Backend.

Provides a hybrid memory system that:
1. Auto-retrieves relevant memories for context
2. Shows memory stats so 120B knows what's available
3. Provides memory_search tool for deep digs
4. Stores new facts from conversations

Uses local Ollama as LLM backend (no cloud API needed for memory operations).
"""
from __future__ import annotations
import os
import re
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from companion_ai.core import config as core_config

logger = logging.getLogger(__name__)

# Ollama model for memory operations (local, fast, private)
OLLAMA_MEM0_MODEL = os.getenv("OLLAMA_MEM0_MODEL", "qwen3:14b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Fallback to Groq if Ollama not available
USE_OLLAMA = os.getenv("MEM0_USE_OLLAMA", "true").lower() == "true"
FALLBACK_GROQ_MODEL = os.getenv("MEM0_LLM_MODEL", "llama-3.1-8b-instant")

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


def _get_mem0_config(use_ollama: bool = True) -> dict:
    """Build Mem0 configuration with Ollama or Groq backend."""
    
    # Use a dedicated path in the data folder for Qdrant storage
    qdrant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mem0_qdrant")

    if use_ollama and USE_OLLAMA:
        # Use local Ollama model
        llm_config = {
            "provider": "ollama",
            "config": {
                "model": OLLAMA_MEM0_MODEL,
                "ollama_base_url": OLLAMA_URL,
                "temperature": 0.1,
                "max_tokens": 1000,
            }
        }
        logger.info(f"🦙 Mem0 using Ollama: {OLLAMA_MEM0_MODEL}")
    else:
        # Fallback to Groq
        api_key = (
            os.getenv("GROQ_MEMORY_API_KEY")
            or (core_config.GROQ_API_KEYS[0] if core_config.GROQ_API_KEYS else None)
            or core_config.GROQ_API_KEY
        )
        llm_config = {
            "provider": "groq",
            "config": {
                "model": FALLBACK_GROQ_MODEL,
                "temperature": 0.1,
                "max_tokens": 1000,
                "api_key": api_key,
            }
        }
        logger.info(f"☁️ Mem0 using Groq: {FALLBACK_GROQ_MODEL}")

    return {
        "llm": llm_config,
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


def _reset_memory(use_ollama: bool = True):
    """(Re)initialize Mem0 with the configured backend."""
    global _memory_instance

    from mem0 import Memory

    config = _get_mem0_config(use_ollama)
    _memory_instance = Memory.from_config(config)
    return _memory_instance


def get_memory() -> Any:
    """Get or create the Mem0 memory instance."""
    global _memory_instance
    
    if _memory_instance is None:
        try:
            _reset_memory(use_ollama=USE_OLLAMA)
            backend = "Ollama" if USE_OLLAMA else "Groq"
            logger.info(f"✅ Mem0 initialized with {backend} backend")
        except ImportError:
            logger.error("Mem0 not installed. Run: pip install mem0ai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Mem0: {e}")
            # Try falling back to Groq if Ollama fails
            if USE_OLLAMA:
                logger.warning("🔄 Ollama failed, falling back to Groq...")
                try:
                    _reset_memory(use_ollama=False)
                    logger.info("✅ Mem0 initialized with Groq fallback")
                except Exception as e2:
                    logger.error(f"Groq fallback also failed: {e2}")
                    raise
            else:
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
    
    We strongly prefer to feed only the user's words to Mem0 so the
    merge model doesn't try to "fix" facts based on assistant phrasing.
    If no user-only content is found, we fall back to the full messages.
    
    Args:
        messages: List of {"role": "user/assistant", "content": "..."}
        user_id: User identifier
        metadata: Optional metadata tags
        
    Returns:
        Result from Mem0
    """
    try:
        memory = get_memory()

        # Snapshot current memories to guard against unsafe UPDATE/DELETE decisions.
        pre_memories = {m.get("id"): m.get("memory", m.get("text")) for m in get_all_memories(user_id)}
        logger.info(f"🧠 Mem0 add start: {len(pre_memories)} existing items for user {user_id}")

        # Add timestamp to metadata
        from datetime import datetime
        if metadata is None:
            metadata = {}
        metadata['created_at'] = datetime.now().isoformat()

        # Keep only user messages to reduce accidental UPDATE/DELETE events.
        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
        payload = [{"role": "user", "content": "\n".join(user_msgs)}] if user_msgs else messages
        
        # Pass metadata to Mem0 (it will be attached to new memories)
        # Note: Mem0's add() might not propagate metadata to all items if extracting multiple facts,
        # but it's the best we can do at this level.
        result = memory.add(payload, user_id=user_id, metadata=metadata)
        
        logger.info(f"🧠 Mem0 add raw result: {result}")

        try:
            result = memory.add(payload, user_id=user_id, metadata=metadata or {})
            logger.info(f"🧠 Mem0 add raw result: {result}")
        except Exception as e:
            error_text = str(e)
            if "model_decommissioned" in error_text or "has been decommissioned" in error_text:
                logger.warning(f"🧠 Mem0 add failed due to decommissioned model '{ACTIVE_MEM0_LLM}'. Falling back to {FALLBACK_MEM0_LLM}.")
                memory = _reset_memory(FALLBACK_MEM0_LLM)
                result = memory.add(payload, user_id=user_id, metadata=metadata or {})
                logger.info(f"🧠 Mem0 add raw result (fallback): {result}")
            else:
                logger.error(f"🧠 Mem0 add failed: {e}")
                raise

        # Guardrails: allow at most 1 delete, and only when texts clearly overlap; allow updates only with overlap.
        restored = []
        delete_budget = 1

        def tokenize(text: str) -> set:
            tokens = re.findall(r"[A-Za-z]+", text.lower())
            return {t for t in tokens if len(t) > 2}

        for item in result.get("results", []) if isinstance(result, dict) else []:
            event = item.get("event")
            mem_id = item.get("id")
            new_text = item.get("text") or item.get("memory") or ""
            original_text = pre_memories.get(mem_id)

            if event in {"DELETE", "UPDATE"} and original_text:
                overlap = tokenize(original_text) & tokenize(new_text)
                allow_update = bool(overlap)
                allow_delete = bool(overlap) and delete_budget > 0

                if event == "DELETE" and allow_delete:
                    delete_budget -= 1
                    continue  # permit this delete

                if event == "UPDATE" and allow_update:
                    continue  # permit this update

                # Otherwise, restore the original fact (convert to NONE behavior)
                memory.add([
                    {"role": "user", "content": original_text}
                ], user_id=user_id, metadata=metadata or {})
                restored.append({"id": mem_id, "text": original_text, "event": event, "overlap": len(overlap)})

        if restored:
            logger.warning(f"🔒 Guarded {len(restored)} unsafe DELETE/UPDATE events; restored originals: {restored}")

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
            # Format with timestamp if available
            for r in results:
                text = r.get("memory", r.get("text", str(r)))
                meta = r.get("metadata") or {}
                created_at = meta.get("created_at")
                
                if created_at:
                    # Try to format nicely if it's ISO
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at)
                        ts_str = dt.strftime("%Y-%m-%d %H:%M")
                        relevant.append(f"[{ts_str}] {text}")
                    except:
                        relevant.append(f"[{created_at}] {text}")
                else:
                    relevant.append(text)
        
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
    lines.append("[Use memory_search(query) to find specific facts in vector DB]")
    
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
    global _memory_instance
    try:
        memory = get_memory()
        memory.delete_all(user_id=user_id)
        logger.info(f"[OK] Cleared all Mem0 memories for user: {user_id}")
        
        # Also try to reset the Qdrant collection to ensure clean state
        try:
            qdrant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mem0_qdrant")
            import shutil
            if os.path.exists(qdrant_path):
                shutil.rmtree(qdrant_path)
                logger.info(f"[OK] Deleted Qdrant data at {qdrant_path}")
        except Exception as qe:
            logger.warning(f"Could not delete Qdrant data: {qe}")
        
        # Force reset the memory instance so next use creates fresh
        _memory_instance = None
        logger.info("[OK] Reset Mem0 instance")
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
