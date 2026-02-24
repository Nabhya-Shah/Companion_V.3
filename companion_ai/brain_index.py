# companion_ai/brain_index.py
"""
Brain Index - Semantic search across brain folder documents.

Uses Ollama embeddings (nomic-embed-text) and SQLite for storage.
Enables asking questions about any document in the brain folder.
"""

import logging
import sqlite3
import json
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import threading
import numpy as np

logger = logging.getLogger(__name__)

# Brain folder location
BRAIN_BASE = Path(__file__).parent.parent / "BRAIN"
INDEX_DB = Path(__file__).parent / "data" / "brain_index.db"

# Chunking settings
CHUNK_SIZE = 500  # tokens (approx chars / 4)
CHUNK_OVERLAP = 50
MAX_CHUNK_CHARS = 2000  # ~500 tokens


class BrainIndex:
    """Semantic search index for brain folder documents."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for storing chunks and embeddings."""
        INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(str(INDEX_DB)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS brain_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    chunk_idx INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(file_path, chunk_idx)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON brain_chunks(file_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON brain_chunks(file_hash)")
            conn.commit()
        
        logger.info(f"🧠 Brain index initialized at {INDEX_DB}")
    
    def _get_file_hash(self, path: Path) -> str:
        """Get hash of file for change detection."""
        stat = path.stat()
        content = f"{path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        words = text.split()
        
        if len(words) <= CHUNK_SIZE:
            return [text.strip()] if text.strip() else []
        
        start = 0
        while start < len(words):
            end = start + CHUNK_SIZE
            chunk = ' '.join(words[start:end])
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - CHUNK_OVERLAP
        
        return chunks
    
    def _extract_text(self, path: Path) -> Optional[str]:
        """Extract text from various file types."""
        suffix = path.suffix.lower()
        
        try:
            if suffix == '.pdf':
                return self._extract_pdf(path)
            elif suffix in ('.txt', '.md', '.json', '.yaml', '.yml'):
                return path.read_text(encoding='utf-8', errors='ignore')
            elif suffix == '.docx':
                return self._extract_docx(path)
            else:
                # Try reading as text
                try:
                    return path.read_text(encoding='utf-8', errors='ignore')
                except:
                    return None
        except Exception as e:
            logger.error(f"Failed to extract text from {path}: {e}")
            return None
    
    def _extract_pdf(self, path: Path) -> Optional[str]:
        """Extract text from PDF."""
        try:
            import pypdf
            with open(path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                texts = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        texts.append(text)
                return '\n\n'.join(texts)
        except ImportError:
            logger.warning("pypdf not installed for PDF extraction")
            return None
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return None
    
    def _extract_docx(self, path: Path) -> Optional[str]:
        """Extract text from Word document."""
        try:
            from docx import Document
            doc = Document(str(path))
            return '\n\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
        except ImportError:
            logger.warning("python-docx not installed for DOCX extraction")
            return None
        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            return None
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text."""
        try:
            from companion_ai.llm_interface import get_embedding
            return get_embedding(text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
    
    def index_file(self, file_path: Path) -> int:
        """Index a single file. Returns number of chunks indexed."""
        with self._lock:
            file_hash = self._get_file_hash(file_path)
            relative_path = str(file_path.relative_to(BRAIN_BASE))
            
            # Check if already indexed with same hash
            with sqlite3.connect(str(INDEX_DB)) as conn:
                existing = conn.execute(
                    "SELECT file_hash FROM brain_chunks WHERE file_path = ? LIMIT 1",
                    (relative_path,)
                ).fetchone()
                
                if existing and existing[0] == file_hash:
                    logger.debug(f"File already indexed: {relative_path}")
                    return 0
                
                # Remove old chunks if file changed
                if existing:
                    conn.execute("DELETE FROM brain_chunks WHERE file_path = ?", (relative_path,))
            
            # Extract text
            text = self._extract_text(file_path)
            if not text or len(text.strip()) < 50:
                logger.debug(f"Skipping {relative_path}: no/little text")
                return 0
            
            # Chunk text
            chunks = self._chunk_text(text)
            if not chunks:
                return 0
            
            logger.info(f"📝 Indexing {relative_path}: {len(chunks)} chunks")
            
            # Generate embeddings and store
            indexed = 0
            with sqlite3.connect(str(INDEX_DB)) as conn:
                for idx, chunk in enumerate(chunks):
                    embedding = self._get_embedding(chunk)
                    if embedding:
                        # Store embedding as binary blob
                        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                        conn.execute("""
                            INSERT OR REPLACE INTO brain_chunks 
                            (file_path, file_hash, chunk_idx, text, embedding)
                            VALUES (?, ?, ?, ?, ?)
                        """, (relative_path, file_hash, idx, chunk, embedding_blob))
                        indexed += 1
                conn.commit()
            
            logger.info(f"✅ Indexed {indexed} chunks from {relative_path}")
            return indexed
    
    def index_all(self) -> Dict[str, int]:
        """Index all files in the brain folder."""
        results = {}
        
        # Supported extensions
        extensions = {'.pdf', '.txt', '.md', '.docx', '.json', '.yaml', '.yml'}
        
        for path in BRAIN_BASE.rglob('*'):
            if path.is_file() and path.suffix.lower() in extensions:
                try:
                    count = self.index_file(path)
                    if count > 0:
                        results[str(path.relative_to(BRAIN_BASE))] = count
                except Exception as e:
                    logger.error(f"Failed to index {path}: {e}")
        
        logger.info(f"🧠 Brain indexing complete: {len(results)} files, {sum(results.values())} chunks")
        return results
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Search for relevant chunks across all indexed documents."""
        # Get query embedding
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
        
        # Load all chunks and calculate similarity
        results = []
        
        with sqlite3.connect(str(INDEX_DB)) as conn:
            rows = conn.execute(
                "SELECT file_path, chunk_idx, text, embedding FROM brain_chunks WHERE embedding IS NOT NULL"
            ).fetchall()
        
        for file_path, chunk_idx, text, embedding_blob in rows:
            if not embedding_blob:
                continue
            
            # Decode embedding
            embedding = np.frombuffer(embedding_blob, dtype=np.float32).tolist()
            
            # Calculate similarity
            similarity = self._cosine_similarity(query_embedding, embedding)
            
            results.append({
                'file': file_path,
                'chunk': chunk_idx,
                'text': text,
                'score': similarity
            })
        
        # Sort by score and return top results
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        with sqlite3.connect(str(INDEX_DB)) as conn:
            total_chunks = conn.execute("SELECT COUNT(*) FROM brain_chunks").fetchone()[0]
            total_files = conn.execute("SELECT COUNT(DISTINCT file_path) FROM brain_chunks").fetchone()[0]
            files = conn.execute(
                "SELECT file_path, COUNT(*) as chunks FROM brain_chunks GROUP BY file_path"
            ).fetchall()
        
        return {
            'total_chunks': total_chunks,
            'total_files': total_files,
            'files': [{'path': f[0], 'chunks': f[1]} for f in files]
        }
    
    def clear(self):
        """Clear all indexed data."""
        with self._lock:
            with sqlite3.connect(str(INDEX_DB)) as conn:
                conn.execute("DELETE FROM brain_chunks")
                conn.commit()
        logger.info("🗑️ Brain index cleared")

    def remove_file(self, relative_path: str) -> bool:
        """Remove all indexed chunks for one relative brain file path."""
        with self._lock:
            with sqlite3.connect(str(INDEX_DB)) as conn:
                cur = conn.execute("DELETE FROM brain_chunks WHERE file_path = ?", (relative_path,))
                conn.commit()
                return cur.rowcount > 0


# Singleton instance
_index: Optional[BrainIndex] = None
_index_lock = threading.Lock()


def get_brain_index() -> BrainIndex:
    """Get the global BrainIndex instance."""
    global _index
    with _index_lock:
        if _index is None:
            _index = BrainIndex()
        return _index


def brain_search(query: str, limit: int = 3) -> str:
    """Search brain documents - tool function. Returns concise results."""
    index = get_brain_index()
    results = index.search(query, limit)
    
    if not results:
        return f"No documents found for '{query}'"
    
    # Only return results with reasonable relevance (>35%)
    relevant = [r for r in results if r['score'] > 0.35]
    if not relevant:
        return f"No closely matching documents for '{query}'"
    
    # Concise output - just file and key excerpt
    output = []
    for r in relevant[:3]:  # Max 3 results
        filename = r['file'].split('\\')[-1]  # Just filename, not path
        score = int(r['score'] * 100)
        excerpt = r['text'][:100].replace('\n', ' ').strip()
        output.append(f"• {filename} ({score}%): {excerpt}...")
    
    return '\n'.join(output)


def start_background_indexing():
    """Start indexing brain folder in background thread."""
    def _index_thread():
        try:
            logger.info("🧠 Starting background brain indexing...")
            index = get_brain_index()
            results = index.index_all()
            logger.info(f"✅ Background indexing complete: {len(results)} files indexed")
        except Exception as e:
            logger.error(f"Background indexing failed: {e}")
    
    thread = threading.Thread(target=_index_thread, daemon=True)
    thread.start()
    return thread
