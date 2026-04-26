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
import time
import logging
import threading
import requests
from datetime import datetime
from uuid import uuid4
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from companion_ai.core import config as core_config
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory import write_queue

logger = logging.getLogger(__name__)

# Ollama model for memory operations (local, fast, private)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Fallback to Groq if Ollama not available
USE_OLLAMA = os.getenv("MEM0_USE_OLLAMA", "true").lower() == "true"

# Keep Mem0 embedding on CPU by default so local Ollama chat can retain GPU VRAM.
MEM0_EMBEDDING_MODEL = os.getenv(
    "MEM0_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
MEM0_EMBEDDER_DEVICE = os.getenv("MEM0_EMBEDDER_DEVICE", "cpu").strip().lower() or "cpu"

# Runtime safeguard: if a CUDA OOM occurs, force subsequent Mem0 embedder inits to CPU.
_mem0_force_cpu_embedder = False

# Serialize Mem0 initialization to avoid concurrent Qdrant local-path lock errors.
_memory_init_lock = threading.Lock()
_mem0_init_backoff_until = 0.0
_mem0_init_last_error = ""


def _is_qdrant_lock_error(message: str | None) -> bool:
    text = str(message or "").lower()
    return "already accessed by another instance of qdrant client" in text


def _is_cuda_oom_error(message: str | None) -> bool:
    text = str(message or "").lower()
    return (
        "cuda error: out of memory" in text
        or "cudaerrormemoryallocation" in text
        or "cuda out of memory" in text
    )


def _get_mem0_embedder_device() -> str:
    if _mem0_force_cpu_embedder:
        return "cpu"
    return MEM0_EMBEDDER_DEVICE


def _get_mem0_ollama_model() -> str:
    """Resolve local Mem0 model with sensible fallbacks for current runtime/profile."""
    def _is_ollama_tag(value: str | None) -> bool:
        token = str(value or "").strip()
        # Ollama models are typically tagged (name:tag). HF model IDs used by vLLM
        # usually omit the ':tag' suffix and cause 404 on /api/chat.
        return bool(token and ":" in token)

    explicit = os.getenv("OLLAMA_MEM0_MODEL") or os.getenv("MEM0_LLM_MODEL")
    candidates: list[str] = []
    if explicit:
        candidates.append(str(explicit).strip())

    try:
        candidate = core_config.get_effective_local_heavy_model()
        if _is_ollama_tag(candidate):
            candidates.append(str(candidate).strip())
    except Exception:
        pass

    try:
        candidate = getattr(core_config, "MEMORY_LOCAL_MODEL", None)
        if _is_ollama_tag(candidate):
            candidates.append(str(candidate).strip())
    except Exception:
        pass

    # Practical fallbacks for common local installs.
    candidates.extend([
        "qwen3.6:35b",
        "gemma4:31b",
        "qwen3:14b",
        "qwen2.5:7b",
    ])

    ordered: list[str] = []
    for item in candidates:
        model = str(item or "").strip()
        if not _is_ollama_tag(model):
            continue
        if model not in ordered:
            ordered.append(model)

    # Prefer models that are actually installed in the local Ollama runtime.
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if response.status_code == 200:
            payload = response.json() if isinstance(response.json(), dict) else {}
            models = payload.get("models", [])
            installed = {
                str(m.get("name") or "").strip()
                for m in models if isinstance(m, dict)
            }
            for model in ordered:
                if model in installed:
                    return model
    except Exception:
        pass

    return ordered[0] if ordered else "qwen3.6:35b"


def _get_mem0_groq_model() -> str:
    """Return the Groq model Mem0 should use for helper operations."""
    return (
        os.getenv("MEM0_LLM_MODEL")
        or getattr(core_config, "MEM0_MODEL", None)
        or getattr(core_config, "MEMORY_FAST_MODEL", None)
        or "llama-3.1-8b-instant"
    )

def get_runtime_descriptor(use_ollama: bool | None = None) -> dict[str, str]:
    """Return the configured Mem0 runtime provider/model for UI and tracing."""
    resolved_use_ollama = USE_OLLAMA if use_ollama is None else use_ollama
    if resolved_use_ollama and USE_OLLAMA:
        return {"provider": "local", "model": _get_mem0_ollama_model()}
    return {"provider": "groq", "model": _get_mem0_groq_model()}


def _get_mem0_groq_api_key() -> str | None:
    """Prefer the fast/tool key so Mem0 helper traffic does not fight 70B extraction."""
    return (
        os.getenv("MEM0_GROQ_API_KEY")
        or os.getenv("GROQ_TOOL_API_KEY")
        or getattr(core_config, "GROQ_TOOL_API_KEY", None)
        or os.getenv("GROQ_MEMORY_API_KEY")
        or (core_config.GROQ_API_KEYS[0] if core_config.GROQ_API_KEYS else None)
        or core_config.GROQ_API_KEY
    )

# Lazy import - only load Mem0 when actually used
_memory_instance = None


def _status_envelope(
    request_id: str,
    status: str,
    backend: str,
    reason: str | None = None,
    committed_at: str | None = None,
) -> dict:
    return {
        'request_id': request_id,
        'status': status,
        'backend': backend,
        'reason': reason,
        'committed_at': committed_at,
    }


def _maybe_existing_committed_status(request_id: str) -> dict | None:
    row = sqlite_memory.get_memory_write_status(request_id)
    if row and row.get('status') == 'accepted_committed':
        return _status_envelope(
            request_id=request_id,
            status='accepted_committed',
            backend=row.get('backend') or 'mem0',
            reason='idempotent_replay',
            committed_at=row.get('committed_at'),
        )
    return None


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
        mem0_model = _get_mem0_ollama_model()
        llm_config = {
            "provider": "ollama",
            "config": {
                "model": mem0_model,
                "ollama_base_url": OLLAMA_URL,
                "temperature": 0.1,
                "max_tokens": 1000,
            }
        }
        logger.info(f"Mem0 using Ollama: {mem0_model}")
    else:
        # Fallback to Groq
        fallback_groq_model = _get_mem0_groq_model()
        api_key = _get_mem0_groq_api_key()
        llm_config = {
            "provider": "groq",
            "config": {
                "model": fallback_groq_model,
                "temperature": 0.1,
                "max_tokens": 1000,
                "api_key": api_key,
            }
        }
        logger.info(f"Mem0 using Groq: {fallback_groq_model}")

    embedder_device = _get_mem0_embedder_device()
    logger.info(
        "Mem0 embedder using HuggingFace model=%s device=%s",
        MEM0_EMBEDDING_MODEL,
        embedder_device,
    )

    return {
        "llm": llm_config,
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": MEM0_EMBEDDING_MODEL,
                "model_kwargs": {"device": embedder_device},
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
    global _memory_instance, _mem0_init_backoff_until, _mem0_init_last_error

    if _memory_instance is not None:
        return _memory_instance

    now = time.time()
    if now < _mem0_init_backoff_until:
        wait_s = int(_mem0_init_backoff_until - now)
        raise RuntimeError(
            f"Mem0 initialization cooling down ({wait_s}s remaining): {_mem0_init_last_error}"
        )

    with _memory_init_lock:
        # Another thread may have initialized Mem0 while we waited.
        if _memory_instance is not None:
            return _memory_instance

        now = time.time()
        if now < _mem0_init_backoff_until:
            wait_s = int(_mem0_init_backoff_until - now)
            raise RuntimeError(
                f"Mem0 initialization cooling down ({wait_s}s remaining): {_mem0_init_last_error}"
            )

        try:
            _reset_memory(use_ollama=USE_OLLAMA)
            backend = "Ollama" if USE_OLLAMA else "Groq"
            logger.info(f"Mem0 initialized with {backend} backend")
            _mem0_init_backoff_until = 0.0
            _mem0_init_last_error = ""
        except ImportError:
            logger.error("Mem0 not installed. Run: pip install mem0ai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Mem0: {e}")
            # Try falling back to Groq if Ollama fails
            if USE_OLLAMA:
                logger.warning("Ollama failed, falling back to Groq...")
                try:
                    _reset_memory(use_ollama=False)
                    logger.info("Mem0 initialized with Groq fallback")
                    _mem0_init_backoff_until = 0.0
                    _mem0_init_last_error = ""
                except Exception as e2:
                    logger.error(f"Groq fallback also failed: {e2}")
                    _mem0_init_last_error = str(e2)
                    cooldown = 45 if _is_qdrant_lock_error(e2) else 15
                    _mem0_init_backoff_until = time.time() + cooldown
                    raise
            else:
                _mem0_init_last_error = str(e)
                cooldown = 45 if _is_qdrant_lock_error(e) else 15
                _mem0_init_backoff_until = time.time() + cooldown
                raise

    return _memory_instance


def add_memory(
    messages: List[Dict[str, str]],
    user_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None,
    request_id: str | None = None,
    allow_queue: bool = True,
) -> Dict[str, Any]:
    """Add memories from a conversation.
    
    SMART DEDUPLICATION: Before adding, we check if a similar fact already exists.
    This prevents saving "Name is Bob" when "Name is Nabhya" is already stored.
    
    Args:
        messages: List of {"role": "user/assistant", "content": "..."}
        user_id: User identifier
        metadata: Optional metadata tags
        
    Returns:
        Result from Mem0
    """
    request_id = request_id or str(uuid4())
    global _mem0_force_cpu_embedder
    existing = _maybe_existing_committed_status(request_id)
    if existing:
        return existing

    envelope = {
        'request_id': request_id,
        'user_scope': user_id or 'default',
        'operation': 'add',
        'payload': {
            'messages': messages,
            'metadata': metadata or {},
        },
        'created_at': datetime.now().isoformat(),
    }

    try:
        memory = get_memory()

        # Snapshot current memories to guard against unsafe UPDATE/DELETE decisions.
        pre_memories = {m.get("id"): m.get("memory", m.get("text")) for m in get_all_memories(user_id)}
        logger.info(f"Mem0 add start: {len(pre_memories)} existing items for user {user_id}")
        
        # SMART DEDUPLICATION: Extract potential fact categories from user message
        user_content = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"])
        
        # Define common fact patterns to check for duplicates
        fact_patterns = [
            ("name is", "name"),
            ("my name is", "name"),
            ("i am called", "name"),
            ("live in", "location"),
            ("i'm from", "location"),
            ("work at", "job"),
            ("i work", "job"),
            ("my job", "job"),
            ("favorite", "preference"),
            ("i prefer", "preference"),
            ("i like", "preference"),
        ]
        
        # Check if message matches a fact pattern
        message_lower = user_content.lower()
        for pattern, category in fact_patterns:
            if pattern in message_lower:
                # Search for existing facts with this category
                existing = search_memories(category, user_id=user_id, limit=5)
                if existing:
                    # Check for semantic overlap using word tokens
                    def tokenize(text: str) -> set:
                        tokens = re.findall(r"[A-Za-z]+", text.lower())
                        return {t for t in tokens if len(t) > 2}
                    
                    new_tokens = tokenize(user_content)
                    for mem in existing:
                        mem_text = mem.get("memory", mem.get("text", ""))
                        mem_tokens = tokenize(mem_text)
                        overlap = new_tokens & mem_tokens
                        # If significant overlap (>30%) and same category, skip
                        if len(overlap) >= 2 and pattern in mem_text.lower():
                            logger.info(f"Skipping duplicate {category} fact - already have: {mem_text}")
                            return {"skipped": True, "reason": f"Similar {category} fact exists", "existing": mem_text}

        # Add timestamp to metadata
        if metadata is None:
            metadata = {}
        metadata['created_at'] = datetime.now().isoformat()

        # Keep only user messages to reduce accidental UPDATE/DELETE events.
        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
        payload = [{"role": "user", "content": "\n".join(user_msgs)}] if user_msgs else messages
        
        # Pass metadata to Mem0 (it will be attached to new memories)
        # Note: Mem0's add() might not propagate metadata to all items if extracting multiple facts,
        # but it's the best we can do at this level.
        try:
            result = memory.add(payload, user_id=user_id, metadata=metadata or {})
            logger.info(f"Mem0 add raw result: {result}")
        except Exception as e:
            error_text = str(e)
            if "model_decommissioned" in error_text or "has been decommissioned" in error_text:
                fallback_groq_model = _get_mem0_groq_model()
                logger.warning(
                    f"Mem0 add failed due to decommissioned model configuration. "
                    f"Falling back to Groq model '{fallback_groq_model}'."
                )
                memory = _reset_memory(use_ollama=False)
                result = memory.add(payload, user_id=user_id, metadata=metadata or {})
                logger.info(f"Mem0 add raw result (fallback): {result}")
            elif _is_cuda_oom_error(error_text):
                logger.warning(
                    "Mem0 add hit CUDA OOM; forcing CPU embedder and retrying once."
                )
                _mem0_force_cpu_embedder = True
                memory = _reset_memory(use_ollama=USE_OLLAMA)
                result = memory.add(payload, user_id=user_id, metadata=metadata or {})
                logger.info(f"Mem0 add raw result (cpu-fallback): {result}")
            else:
                logger.error(f"Mem0 add failed: {e}")
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
            logger.warning(f"Guarded {len(restored)} unsafe DELETE/UPDATE events; restored originals: {restored}")

        committed_at = datetime.now().isoformat()
        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='add',
            status='accepted_committed',
            backend='mem0',
            payload=envelope.get('payload'),
            committed_at=committed_at,
        )

        if isinstance(result, dict):
            result.setdefault("runtime", get_runtime_descriptor(use_ollama=USE_OLLAMA))
            result['write_status'] = _status_envelope(
                request_id=request_id,
                status='accepted_committed',
                backend='mem0',
                committed_at=committed_at,
            )
        logger.info(f"Added memories for user {user_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        if allow_queue:
            queued = write_queue.enqueue_write(envelope)
            sqlite_memory.log_memory_write_status(
                request_id=request_id,
                user_scope=user_id,
                operation='add',
                status='accepted_queued',
                backend='spool',
                reason=str(e),
                payload=envelope.get('payload'),
            )
            queued['reason'] = str(e)
            return {'error': str(e), 'write_status': queued}

        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='add',
            status='failed',
            backend='mem0',
            reason=str(e),
            payload=envelope.get('payload'),
        )
        return {'error': str(e), 'write_status': _status_envelope(request_id, 'failed', 'mem0', reason=str(e))}


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
        try:
            response = memory.search(query, user_id=user_id, limit=limit)
        except Exception as e:
            msg = str(e)
            if "Top-level entity parameters" in msg and "user_id" in msg:
                # Mem0 >=2.0 expects scoped entity filters instead of top-level user_id.
                try:
                    response = memory.search(query, filters={"user_id": user_id}, limit=limit)
                except Exception:
                    response = memory.search(query, filter={"user_id": user_id}, limit=limit)
            else:
                raise
        # Mem0 returns {'results': [...]}
        results = response.get('results', []) if isinstance(response, dict) else response
        results = sqlite_memory.rank_memories_by_quality(results, user_scope=user_id, query=query)
        logger.info(f"Found {len(results)} memories for query: {query[:50]}")
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
        try:
            response = memory.get_all(user_id=user_id)
        except Exception as e:
            msg = str(e)
            if "Top-level entity parameters" in msg and "user_id" in msg:
                try:
                    response = memory.get_all(filters={"user_id": user_id})
                except Exception:
                    response = memory.get_all(filter={"user_id": user_id})
            else:
                raise
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
                if r.get('quality_contradiction_state') == 'conflict':
                    continue
                text = r.get("memory", r.get("text", str(r)))
                meta = r.get("metadata") or {}
                created_at = meta.get("created_at")
                q_label = r.get('quality_confidence_label')
                prefix = f"[{q_label}] " if q_label else ""
                
                if created_at:
                    # Try to format nicely if it's ISO
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at)
                        ts_str = dt.strftime("%Y-%m-%d %H:%M")
                        relevant.append(f"[{ts_str}] {prefix}{text}")
                    except:
                        relevant.append(f"[{created_at}] {prefix}{text}")
                else:
                    relevant.append(f"{prefix}{text}")
        
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
    result = delete_memory_with_status(memory_id)
    return result.get('status') in {'accepted_committed', 'accepted_queued'}


def delete_memory_with_status(
    memory_id: str,
    user_id: str = "default",
    request_id: str | None = None,
    allow_queue: bool = True,
) -> dict:
    """Delete memory with explicit write status envelope."""
    request_id = request_id or str(uuid4())
    existing = _maybe_existing_committed_status(request_id)
    if existing:
        return existing

    envelope = {
        'request_id': request_id,
        'user_scope': user_id or 'default',
        'operation': 'delete',
        'payload': {'memory_id': memory_id},
        'created_at': datetime.now().isoformat(),
    }

    try:
        memory = get_memory()
        memory.delete(memory_id)
        committed_at = datetime.now().isoformat()
        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='delete',
            status='accepted_committed',
            backend='mem0',
            payload=envelope['payload'],
            committed_at=committed_at,
        )
        logger.info(f"Deleted memory: {memory_id}")
        return _status_envelope(request_id, 'accepted_committed', 'mem0', committed_at=committed_at)
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        if allow_queue:
            queued = write_queue.enqueue_write(envelope)
            sqlite_memory.log_memory_write_status(
                request_id=request_id,
                user_scope=user_id,
                operation='delete',
                status='accepted_queued',
                backend='spool',
                reason=str(e),
                payload=envelope['payload'],
            )
            queued['reason'] = str(e)
            return queued
        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='delete',
            status='failed',
            backend='mem0',
            reason=str(e),
            payload=envelope['payload'],
        )
        return _status_envelope(request_id, 'failed', 'mem0', reason=str(e))


def update_memory(memory_id: str, new_data: str) -> bool:
    """Update a specific memory.
    
    Args:
        memory_id: The memory ID to update
        new_data: The new text content for the memory
        
    Returns:
        True if successful
    """
    result = update_memory_with_status(memory_id, new_data)
    return result.get('status') in {'accepted_committed', 'accepted_queued'}


def update_memory_with_status(
    memory_id: str,
    new_data: str,
    user_id: str = "default",
    request_id: str | None = None,
    allow_queue: bool = True,
) -> dict:
    """Update memory with explicit write status envelope."""
    request_id = request_id or str(uuid4())
    existing = _maybe_existing_committed_status(request_id)
    if existing:
        return existing

    envelope = {
        'request_id': request_id,
        'user_scope': user_id or 'default',
        'operation': 'update',
        'payload': {'memory_id': memory_id, 'new_data': new_data},
        'created_at': datetime.now().isoformat(),
    }

    try:
        memory = get_memory()
        memory.update(memory_id, data=new_data)
        committed_at = datetime.now().isoformat()
        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='update',
            status='accepted_committed',
            backend='mem0',
            payload=envelope['payload'],
            committed_at=committed_at,
        )
        logger.info(f"Updated memory {memory_id}: {new_data[:50]}...")
        return _status_envelope(request_id, 'accepted_committed', 'mem0', committed_at=committed_at)
    except Exception as e:
        logger.error(f"Failed to update memory: {e}")
        if allow_queue:
            queued = write_queue.enqueue_write(envelope)
            sqlite_memory.log_memory_write_status(
                request_id=request_id,
                user_scope=user_id,
                operation='update',
                status='accepted_queued',
                backend='spool',
                reason=str(e),
                payload=envelope['payload'],
            )
            queued['reason'] = str(e)
            return queued
        sqlite_memory.log_memory_write_status(
            request_id=request_id,
            user_scope=user_id,
            operation='update',
            status='failed',
            backend='mem0',
            reason=str(e),
            payload=envelope['payload'],
        )
        return _status_envelope(request_id, 'failed', 'mem0', reason=str(e))


def replay_queued_writes(max_items: int | None = None) -> dict:
    """Replay durable queued writes to Mem0 backends."""

    def _handler(envelope: dict) -> dict:
        req_id = envelope.get('request_id') or str(uuid4())
        op = (envelope.get('operation') or 'add').strip().lower()
        payload = envelope.get('payload') or {}
        user_scope = envelope.get('user_scope') or 'default'

        existing = _maybe_existing_committed_status(req_id)
        if existing:
            return existing

        if op == 'add':
            messages = payload.get('messages') or []
            metadata = payload.get('metadata') or {}
            result = add_memory(
                messages=messages,
                user_id=user_scope,
                metadata=metadata,
                request_id=req_id,
                allow_queue=False,
            )
            if isinstance(result, dict):
                return result.get('write_status') or _status_envelope(req_id, 'failed', 'mem0', reason='missing_write_status')
            return _status_envelope(req_id, 'failed', 'mem0', reason='invalid_add_result')

        if op == 'delete':
            return delete_memory_with_status(
                memory_id=payload.get('memory_id', ''),
                user_id=user_scope,
                request_id=req_id,
                allow_queue=False,
            )

        if op == 'update':
            return update_memory_with_status(
                memory_id=payload.get('memory_id', ''),
                new_data=payload.get('new_data', ''),
                user_id=user_scope,
                request_id=req_id,
                allow_queue=False,
            )

        sqlite_memory.log_memory_write_status(
            request_id=req_id,
            user_scope=user_scope,
            operation=op,
            status='failed',
            backend='replay',
            reason='unknown_operation',
            payload=payload,
        )
        return _status_envelope(req_id, 'failed', 'replay', reason='unknown_operation')

    return write_queue.replay_writes(_handler, max_items=max_items)

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


def migrate_legacy_memories(
    source_user_id: str,
    target_user_id: str,
    max_items: int = 200,
) -> Dict[str, Any]:
    """Migrate legacy memories from one Mem0 user scope to another.

    This is used during session/profile scope rollout to copy old
    single-user memories into new scoped IDs.
    """
    if not source_user_id or not target_user_id:
        return {"migrated": 0, "skipped": 0, "error": "invalid_user_id"}
    if source_user_id == target_user_id:
        return {"migrated": 0, "skipped": 0, "reason": "same_scope"}

    try:
        source_memories = get_all_memories(source_user_id)
        if not source_memories:
            return {"migrated": 0, "skipped": 0, "reason": "source_empty"}

        target_memories = get_all_memories(target_user_id)
        existing_texts = {
            (m.get("memory") or m.get("text") or "").strip().lower()
            for m in target_memories
            if (m.get("memory") or m.get("text"))
        }

        migrated = 0
        skipped = 0

        for item in source_memories[:max_items]:
            text = (item.get("memory") or item.get("text") or "").strip()
            if not text:
                skipped += 1
                continue

            key = text.lower()
            if key in existing_texts:
                skipped += 1
                continue

            add_memory(
                [{"role": "user", "content": text}],
                user_id=target_user_id,
                metadata={"migrated_from": source_user_id, "migration": "legacy_scope"},
            )
            existing_texts.add(key)
            migrated += 1

        logger.info(
            f"Mem0 migration {source_user_id} -> {target_user_id}: migrated={migrated}, skipped={skipped}"
        )
        return {"migrated": migrated, "skipped": skipped, "source_total": len(source_memories)}
    except Exception as e:
        logger.error(f"Mem0 migration failed ({source_user_id} -> {target_user_id}): {e}")
        return {"migrated": 0, "skipped": 0, "error": str(e)}


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
    
    lines = [f"Memory Search: '{query}'", ""]
    for i, r in enumerate(results, 1):
        mem = r.get("memory", r.get("text", str(r)))
        score = r.get("score", 0)
        lines.append(f"{i}. {mem} (relevance: {score:.2f})")
    
    return "\n".join(lines)
