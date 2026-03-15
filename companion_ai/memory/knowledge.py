# companion_ai/memory/knowledge.py
"""
Unified Knowledge Entry Point (P5-D3)

All knowledge storage and retrieval goes through two functions:

    remember(fact, ...)   — store a fact across backends
    recall(query, ...)    — search all backends, merge, rank, dedup

Backends:
    1. Mem0 (vector DB — semantic search)
    2. SQLite user_profile (structured facts with confidence)
    3. Brain Index (chunked document embeddings)

This module replaces ad-hoc dual/triple writes scattered across
orchestrator, conversation_manager, and memory_loop.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# remember()
# ---------------------------------------------------------------------------

def remember(
    fact: str,
    *,
    key: str | None = None,
    confidence: float = 0.7,
    source: str = "conversation",
    evidence: str | None = None,
    user_id: str | None = None,
    skip_mem0: bool = False,
    skip_sqlite: bool = False,
) -> dict[str, Any]:
    """Store a fact across active backends.

    Args:
        fact: The fact text (e.g. "User's name is Nabhya").
        key: Optional kebab-case key for the SQLite profile row.
             If omitted, the fact is stored in Mem0 only.
        confidence: 0.0–1.0 confidence score.
        source: Provenance tag (e.g. ``'conversation'``, ``'loop_memory'``).
        evidence: Optional evidence text / quote.
        user_id: Mem0 user scope.  Defaults to config ``MEM0_USER_ID``.
        skip_mem0: If True, skip Mem0 storage.
        skip_sqlite: If True, skip SQLite profile upsert.

    Returns:
        ``{"mem0": ..., "sqlite": bool}`` summarising what was written.
    """
    from companion_ai.core import config as core_config

    effective_user_id = user_id or core_config.MEM0_USER_ID
    result: dict[str, Any] = {"mem0": None, "sqlite": False}

    # --- Mem0 vector store ---
    if not skip_mem0 and core_config.USE_MEM0:
        try:
            from companion_ai.memory.mem0_backend import add_memory
            messages = [{"role": "user", "content": fact}]
            mem0_out = add_memory(
                messages=messages,
                user_id=effective_user_id,
                metadata={"source": source},
            )
            result["mem0"] = mem0_out
            logger.info(f"knowledge.remember -> Mem0 OK: {fact[:60]}")
        except Exception as e:
            logger.warning(f"knowledge.remember Mem0 failed: {e}")

    # --- SQLite profile fact ---
    if not skip_sqlite and key:
        try:
            from companion_ai.memory.sqlite_backend import upsert_profile_fact
            upsert_profile_fact(
                key=key,
                value=fact,
                confidence=confidence,
                source=source,
                evidence=evidence,
            )
            result["sqlite"] = True
            logger.info(f"knowledge.remember -> SQLite OK: {key}={fact[:60]}")
        except Exception as e:
            logger.warning(f"knowledge.remember SQLite failed: {e}")

    # --- Persona micro-evolution on high-importance facts ---
    try:
        from companion_ai.services.persona import on_memory_event
        on_memory_event(fact, importance=confidence)
    except Exception:
        pass  # never break remember() for persona

    return result


# ---------------------------------------------------------------------------
# recall()
# ---------------------------------------------------------------------------

def recall(
    query: str,
    *,
    limit: int = 10,
    user_id: str | None = None,
    include_brain: bool = True,
    include_mem0: bool = True,
    include_sqlite: bool = True,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Search all knowledge backends, merge, rank, and deduplicate.

    Each result dict has at least:
        ``text``, ``score``, ``source`` (``'mem0'|'brain'|'profile'|'summary'|'insight'``)

    Results are sorted by ``score`` descending and capped at *limit*.
    """
    from companion_ai.core import config as core_config

    effective_user_id = user_id or core_config.MEM0_USER_ID
    raw_results: list[dict[str, Any]] = []

    # --- Mem0 vector search ---
    if include_mem0 and core_config.USE_MEM0:
        try:
            from companion_ai.memory.mem0_backend import search_memories
            mem0_hits = search_memories(query, user_id=effective_user_id, limit=limit)
            for m in mem0_hits:
                text = m.get("memory", m.get("text", ""))
                if not text:
                    continue
                score = float(m.get("score", 0.5))
                raw_results.append({
                    "text": text,
                    "score": score,
                    "source": "mem0",
                    "id": m.get("id"),
                    "surfacing_reason": "Vector semantic match",
                    "score_breakdown": {"vector_score": score}
                })
        except Exception as e:
            logger.warning(f"recall Mem0 failed: {e}")

    # --- SQLite profile facts + summaries + insights ---
    if include_sqlite:
        try:
            from companion_ai.memory.sqlite_backend import search_memory
            sqlite_hits = search_memory(query, limit=limit)
            for hit in sqlite_hits:
                raw_results.append({
                    "text": hit["text"],
                    "score": float(hit.get("score", 0.3)),
                    "source": hit.get("type", "profile"),
                    "surfacing_reason": hit.get("surfacing_reason", "SQLite keyword match"),
                    "score_breakdown": hit.get("score_breakdown", {})
                })
        except Exception as e:
            logger.warning(f"recall SQLite failed: {e}")

    # --- Brain index (document chunks) ---
    if include_brain:
        try:
            from companion_ai.brain_index import get_brain_index
            index = get_brain_index()
            brain_hits = index.search(query, limit=limit)
            for hit in brain_hits:
                score = float(hit.get("score", 0.0))
                if score < 0.35:
                    continue  # below relevance floor
                raw_results.append({
                    "text": hit["text"],
                    "score": score,
                    "source": "brain",
                    "file": hit.get("file"),
                    "surfacing_reason": "Document content match",
                    "score_breakdown": {"bm25_score": score}
                })
        except Exception as e:
            logger.warning(f"recall BrainIndex failed: {e}")

    # --- Dedup by text similarity ---
    deduped = _dedup_results(raw_results)

    # --- Filter by min_score ---
    if min_score > 0:
        deduped = [r for r in deduped if r["score"] >= min_score]

    # --- Sort and cap ---
    deduped.sort(key=lambda r: r["score"], reverse=True)
    return deduped[:limit]


def recall_context(query: str, *, limit: int = 8, user_id: str | None = None, **kwargs) -> str:
    """Convenience wrapper: recall + format as a text block for prompt injection."""
    results = recall(query, limit=limit, user_id=user_id, **kwargs)
    if not results:
        return ""
    lines = []
    for r in results:
        src = r["source"]
        reason = r.get("surfacing_reason", "Relevance match")
        text = r["text"].replace("\n", " ").strip()
        if len(text) > 200:
            text = text[:197] + "..."
        lines.append(f"- [{src} | {reason}] {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dedup_results(results: list[dict]) -> list[dict]:
    """Remove near-duplicate results keeping the highest-scored version."""
    if len(results) <= 1:
        return results

    seen_texts: list[str] = []
    deduped: list[dict] = []

    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        text_lower = r["text"].lower().strip()
        is_dup = False
        for seen in seen_texts:
            # Simple token-overlap dedup (>=80% overlap → dup)
            tokens_a = set(text_lower.split())
            tokens_b = set(seen.split())
            if not tokens_a or not tokens_b:
                continue
            overlap = len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))
            if overlap >= 0.80:
                is_dup = True
                break
        if not is_dup:
            seen_texts.append(text_lower)
            deduped.append(r)

    return deduped
