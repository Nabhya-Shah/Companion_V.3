"""
Memory RAG Integration - Enhanced memory search with BGE-M3 and reranking.

This module enhances the existing memory_v2.py with:
1. Semantic search using BGE-M3 embeddings
2. Reranking with BGE-Reranker-V2-M3 for higher accuracy
3. Hybrid search combining Mem0 and local document retrieval
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy imports to avoid loading models on import
_rag_service = None


def _get_rag_service():
    """Lazy-load RAG service to avoid slow startup."""
    global _rag_service
    if _rag_service is None:
        from companion_ai.rag_service import RAGService
        _rag_service = RAGService()
    return _rag_service


@dataclass
class EnhancedMemoryResult:
    """Result from enhanced memory search."""
    text: str
    score: float
    source: str  # 'mem0' or 'document'
    memory_id: Optional[str] = None
    metadata: Optional[Dict] = None


def enhance_memory_search(
    query: str,
    mem0_results: List[Dict[str, Any]],
    additional_documents: Optional[List[str]] = None,
    use_reranking: bool = True,
    top_k: int = 5
) -> List[EnhancedMemoryResult]:
    """
    Enhance Mem0 search results with RAG reranking.
    
    Args:
        query: Search query
        mem0_results: Results from Mem0.search()
        additional_documents: Optional extra documents to include
        use_reranking: Whether to apply cross-encoder reranking
        top_k: Number of results to return
        
    Returns:
        Reranked list of EnhancedMemoryResult
    """
    if not mem0_results and not additional_documents:
        return []
    
    # Extract texts from Mem0 results
    texts = []
    sources = []
    memory_ids = []
    metadata_list = []
    
    for r in mem0_results:
        text = r.get("memory", r.get("text", str(r)))
        texts.append(text)
        sources.append("mem0")
        memory_ids.append(r.get("id"))
        metadata_list.append(r.get("metadata"))
    
    # Add additional documents
    if additional_documents:
        for doc in additional_documents:
            texts.append(doc)
            sources.append("document")
            memory_ids.append(None)
            metadata_list.append(None)
    
    if not texts:
        return []
    
    # Apply reranking if requested
    if use_reranking and len(texts) > 1:
        try:
            rag = _get_rag_service()
            reranked = rag.reranker.rerank(query, texts, top_k=top_k)
            
            results = []
            for idx, score in reranked:
                results.append(EnhancedMemoryResult(
                    text=texts[idx],
                    score=score,
                    source=sources[idx],
                    memory_id=memory_ids[idx],
                    metadata=metadata_list[idx]
                ))
            return results
        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
    
    # Fallback: return original order with dummy scores
    results = []
    for i, text in enumerate(texts[:top_k]):
        results.append(EnhancedMemoryResult(
            text=text,
            score=1.0 - (i * 0.1),  # Descending score
            source=sources[i],
            memory_id=memory_ids[i],
            metadata=metadata_list[i]
        ))
    return results


def semantic_document_search(
    query: str,
    documents: List[str],
    top_k: int = 5,
    use_reranking: bool = True
) -> List[EnhancedMemoryResult]:
    """
    Semantic search over documents with optional reranking.
    
    Args:
        query: Search query
        documents: List of document texts
        top_k: Number of results
        use_reranking: Whether to use reranking
        
    Returns:
        Search results sorted by relevance
    """
    if not documents:
        return []
    
    try:
        rag = _get_rag_service()
        
        if use_reranking:
            results = rag.retrieve_and_rerank(
                query, documents,
                initial_k=min(20, len(documents)),
                final_k=top_k
            )
        else:
            from companion_ai.rag_service import get_embedding_service
            results = get_embedding_service().retrieve(query, documents, top_k=top_k)
        
        return [
            EnhancedMemoryResult(
                text=r.text,
                score=r.score,
                source="document",
                metadata=r.metadata
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []


def build_enhanced_memory_context(
    user_message: str,
    user_id: str = "default",
    max_memories: int = 5,
    additional_context: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Build enhanced memory context with RAG for better retrieval.
    
    Args:
        user_message: Current user message
        user_id: User identifier
        max_memories: Max memories to include
        additional_context: Optional extra context documents
        
    Returns:
        Dict with 'memories', 'context_text', and 'stats'
    """
    try:
        # Get Mem0 memories
        from companion_ai.memory_v2 import search_memories, get_memory_stats
        
        mem0_results = search_memories(user_message, user_id, limit=max_memories * 2)
        stats = get_memory_stats(user_id)
        
        # Enhance with reranking
        enhanced = enhance_memory_search(
            query=user_message,
            mem0_results=mem0_results,
            additional_documents=additional_context,
            use_reranking=True,
            top_k=max_memories
        )
        
        # Build context text
        context_parts = []
        for r in enhanced:
            if r.source == "mem0":
                context_parts.append(f"[Memory] {r.text}")
            else:
                context_parts.append(f"[Context] {r.text}")
        
        context_text = "\n".join(context_parts) if context_parts else ""
        
        return {
            "memories": enhanced,
            "context_text": context_text,
            "stats": {
                "total_memories": stats.total_memories,
                "retrieved": len(enhanced),
                "reranked": True
            }
        }
    except Exception as e:
        logger.error(f"Failed to build enhanced memory context: {e}")
        return {
            "memories": [],
            "context_text": "",
            "stats": {"total_memories": 0, "retrieved": 0, "reranked": False}
        }


# Convenience function for quick testing
def test_rag_memory():
    """Quick test of RAG memory integration."""
    print("Testing RAG Memory Integration...")
    
    # Test with sample documents
    docs = [
        "The user's name is John and he loves Python programming",
        "John has a meeting tomorrow at 3pm with the engineering team",
        "The weather today is sunny with 25 degrees celsius",
        "John prefers dark mode in all his applications",
        "The project deadline is next Friday"
    ]
    
    query = "What does John like?"
    
    print(f"\nQuery: {query}")
    print("-" * 50)
    
    results = semantic_document_search(query, docs, top_k=3)
    
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r.score:.3f}] {r.text}")
    
    print("\n[OK] Test complete!")
    return results


if __name__ == "__main__":
    test_rag_memory()
