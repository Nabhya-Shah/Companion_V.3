"""
RAG Service - Embeddings and Reranking for Document Retrieval

Uses:
- BAAI/bge-m3 for embeddings (8K context, multilingual)
- BAAI/bge-reranker-v2-m3 for reranking (cross-encoder)

These models significantly improve retrieval quality for RAG pipelines,
reducing hallucinations by ~35% compared to baseline retrievers.
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from retrieval with optional reranking."""
    text: str
    score: float
    metadata: Optional[Dict] = None


class EmbeddingService:
    """
    Embedding service using BGE-M3.
    
    Features:
    - 8192 token context window
    - Multilingual support (100+ languages)
    - Dense, sparse, and multi-vector retrieval
    """
    
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the embedding model."""
        if self._initialized:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._initialized = True
            logger.info(f"Embedding model loaded successfully (dim={self._model.get_sentence_embedding_dimension()})")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            # Fallback to CPU
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Retrying with CPU...")
                self._model = SentenceTransformer(self.model_name, device="cpu")
                self._initialized = True
                logger.info("Embedding model loaded on CPU")
            except Exception as e2:
                logger.error(f"Failed to load embedding model on CPU: {e2}")
                raise
    
    def embed(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        """
        Generate embeddings for text(s).
        
        Args:
            texts: Single text or list of texts to embed
            normalize: Whether to L2 normalize the embeddings
            
        Returns:
            numpy array of shape (n_texts, embedding_dim)
        """
        self._ensure_initialized()
        
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 10
        )
        
        return embeddings
    
    def embed_query(self, query: str) -> np.ndarray:
        """Embed a query for retrieval."""
        return self.embed(query, normalize=True)[0]
    
    def embed_documents(self, documents: List[str]) -> np.ndarray:
        """Embed documents for indexing."""
        return self.embed(documents, normalize=True)
    
    def similarity(self, query_embedding: np.ndarray, doc_embeddings: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarity between query and documents.
        
        Args:
            query_embedding: Query embedding (1D array)
            doc_embeddings: Document embeddings (2D array)
            
        Returns:
            Similarity scores for each document
        """
        # Ensure 2D
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        
        # Cosine similarity (embeddings are already normalized)
        scores = np.dot(doc_embeddings, query_embedding.T).flatten()
        return scores
    
    def retrieve(
        self,
        query: str,
        documents: List[str],
        top_k: int = 10,
        metadata: Optional[List[Dict]] = None
    ) -> List[RetrievalResult]:
        """
        Retrieve top-k documents for a query using semantic search.
        
        Args:
            query: The search query
            documents: List of documents to search
            top_k: Number of results to return
            metadata: Optional metadata for each document
            
        Returns:
            Top-k documents with scores
        """
        if not documents:
            return []
        
        query_emb = self.embed_query(query)
        doc_embs = self.embed_documents(documents)
        
        scores = self.similarity(query_emb, doc_embs)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            result = RetrievalResult(
                text=documents[idx],
                score=float(scores[idx]),
                metadata=metadata[idx] if metadata else None
            )
            results.append(result)
        
        return results
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        self._ensure_initialized()
        return self._model.get_sentence_embedding_dimension()


class RerankerService:
    """
    Reranker service using BGE-Reranker-V2-M3.
    
    Features:
    - Cross-encoder architecture for high accuracy
    - Multilingual support
    - ~35% reduction in hallucinations
    """
    
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the reranker model."""
        if self._initialized:
            return
        
        try:
            from FlagEmbedding import FlagReranker
            logger.info(f"Loading reranker model: {self.model_name}")
            self._model = FlagReranker(self.model_name, device=self.device)
            self._initialized = True
            logger.info("Reranker model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load reranker model: {e}")
            # Fallback to CPU
            try:
                from FlagEmbedding import FlagReranker
                logger.info("Retrying with CPU...")
                self._model = FlagReranker(self.model_name, device="cpu")
                self._initialized = True
                logger.info("Reranker model loaded on CPU")
            except Exception as e2:
                logger.error(f"Failed to load reranker model on CPU: {e2}")
                raise
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None
    ) -> List[Tuple[int, float]]:
        """
        Rerank documents by relevance to query.
        
        Args:
            query: The search query
            documents: List of documents to rerank
            top_k: Optional limit on results
            
        Returns:
            List of (document_index, score) tuples, sorted by score descending
        """
        self._ensure_initialized()
        
        if not documents:
            return []
        
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Get scores from cross-encoder
        scores = self._model.compute_score(pairs)
        
        # Handle single document case
        if isinstance(scores, (int, float)):
            scores = [scores]
        
        # Create (index, score) pairs and sort by score
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores)]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        
        if top_k:
            indexed_scores = indexed_scores[:top_k]
        
        return indexed_scores
    
    def rerank_results(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        Rerank retrieval results.
        
        Args:
            query: The search query
            results: List of RetrievalResults to rerank
            top_k: Optional limit on results
            
        Returns:
            Reranked results with updated scores
        """
        if not results:
            return []
        
        documents = [r.text for r in results]
        reranked = self.rerank(query, documents, top_k)
        
        reranked_results = []
        for idx, score in reranked:
            result = RetrievalResult(
                text=results[idx].text,
                score=score,
                metadata=results[idx].metadata
            )
            reranked_results.append(result)
        
        return reranked_results


class RAGService:
    """
    Combined RAG service with embedding retrieval and reranking.
    
    Two-stage retrieval:
    1. Fast semantic search with embeddings (retrieve top-N candidates)
    2. Precise reranking with cross-encoder (select top-K)
    """
    
    def __init__(
        self,
        embedding_model: str = "BAAI/bge-m3",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu"  # CPU default for Windows compatibility
    ):
        self.embeddings = EmbeddingService(embedding_model, device)
        self.reranker = RerankerService(reranker_model, device)
    
    def retrieve_and_rerank(
        self,
        query: str,
        documents: List[str],
        initial_k: int = 20,
        final_k: int = 5,
        metadata: Optional[List[Dict]] = None
    ) -> List[RetrievalResult]:
        """
        Two-stage retrieval with reranking.
        
        Args:
            query: The search query
            documents: All documents to search
            initial_k: Number of candidates from embedding search
            final_k: Number of results after reranking
            metadata: Optional metadata for each document
            
        Returns:
            Top-k reranked results
        """
        # Stage 1: Fast embedding-based retrieval
        candidates = self.embeddings.retrieve(
            query,
            documents,
            top_k=initial_k,
            metadata=metadata
        )
        
        if not candidates:
            return []
        
        # Stage 2: Precise reranking
        reranked = self.reranker.rerank_results(query, candidates, top_k=final_k)
        
        return reranked


# Singleton instances
_embedding_service: Optional[EmbeddingService] = None
_reranker_service: Optional[RerankerService] = None
_rag_service: Optional[RAGService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_reranker_service() -> RerankerService:
    """Get the global reranker service instance."""
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service


def get_rag_service() -> RAGService:
    """Get the global RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


# Convenience functions
def embed_text(text: str) -> np.ndarray:
    """Quick text embedding."""
    return get_embedding_service().embed_query(text)


def retrieve_documents(
    query: str,
    documents: List[str],
    top_k: int = 5,
    use_reranking: bool = True
) -> List[RetrievalResult]:
    """
    Quick document retrieval.
    
    Args:
        query: Search query
        documents: Documents to search
        top_k: Number of results
        use_reranking: Whether to use cross-encoder reranking
        
    Returns:
        Retrieved documents with scores
    """
    if use_reranking:
        return get_rag_service().retrieve_and_rerank(
            query, documents,
            initial_k=min(20, len(documents)),
            final_k=top_k
        )
    else:
        return get_embedding_service().retrieve(query, documents, top_k=top_k)
