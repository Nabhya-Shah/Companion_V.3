# companion_ai/memory.py
import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone
import hashlib

# Define database path
MODULE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
DB_PATH = os.path.join(DATA_DIR, 'companion_ai.db')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database tables with enhanced schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Enhanced user profile table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'conversation'
        )
    ''')
    
    # Enhanced conversation summaries with deduplication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary_text TEXT NOT NULL,
            content_hash TEXT UNIQUE,
            relevance_score REAL DEFAULT 1.0
        )
    ''')
    
    # Enhanced insights with similarity checking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            insight_text TEXT NOT NULL,
            content_hash TEXT UNIQUE,
            category TEXT DEFAULT 'general',
            relevance_score REAL DEFAULT 1.0
        )
    ''')
    
    # Memory consolidation log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_consolidation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            details TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"INFO: Enhanced database initialized at {DB_PATH}")

# Utility functions
def generate_content_hash(text: str) -> str:
    """Generate a hash for content deduplication."""
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Simple similarity calculation based on normalized word overlap.

    Normalization steps:
      - lowercase
      - strip basic punctuation suffixes ,.;:!?
      - singularize basic trailing 's' (naive) for rough matching
    """
    def norm_words(t: str) -> set[str]:
        out = set()
        for raw in t.lower().split():
            w = raw.strip(",.;:!?")
            if w.endswith('s') and len(w) > 3:
                w = w[:-1]
            if w:
                out.add(w)
        return out
    words1 = norm_words(text1)
    words2 = norm_words(text2)
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

# Enhanced Profile functions
def upsert_profile_fact(key: str, value: str, confidence: float = 1.0, source: str = 'conversation'):
    """Insert or update profile fact with confidence scoring."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if key exists and compare values
    cursor.execute("SELECT value, confidence FROM user_profile WHERE key = ?", (key,))
    existing = cursor.fetchone()
    
    if existing:
        existing_value, existing_confidence = existing
        # If new confidence is higher or values are different, update
        if confidence > existing_confidence or existing_value != value:
            cursor.execute('''
                UPDATE user_profile 
                SET value = ?, confidence = ?, last_updated = CURRENT_TIMESTAMP, source = ?
                WHERE key = ?
            ''', (value, confidence, source, key))
            print(f"📝 Updated profile: {key} = {value} (confidence: {confidence:.2f})")
    else:
        cursor.execute('''
            INSERT INTO user_profile (key, value, confidence, source) 
            VALUES (?, ?, ?, ?)
        ''', (key, value, confidence, source))
        print(f"📝 New profile fact: {key} = {value}")
    
    conn.commit()
    conn.close()

def get_profile_fact(key: str) -> str | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_all_profile_facts() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM user_profile")
    results = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in results}

# Enhanced Summary functions with deduplication
def add_summary(summary_text: str, relevance_score: float = 1.0):
    """Add summary with deduplication and similarity checking."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    content_hash = generate_content_hash(summary_text)
    
    # Check for exact duplicates
    cursor.execute("SELECT id FROM conversation_summaries WHERE content_hash = ?", (content_hash,))
    if cursor.fetchone():
        print("🔄 Duplicate summary detected, skipping...")
        conn.close()
        return
    
    # Check for similar summaries (>70% similarity)
    cursor.execute("SELECT summary_text FROM conversation_summaries ORDER BY timestamp DESC LIMIT 10")
    recent_summaries = cursor.fetchall()
    
    for row in recent_summaries:
        similarity = calculate_text_similarity(summary_text, row[0])
        if similarity > 0.7:
            print(f"🔄 Similar summary detected ({similarity:.2f} similarity), skipping...")
            conn.close()
            return
    
    # Add new summary
    cursor.execute('''
        INSERT INTO conversation_summaries (summary_text, content_hash, relevance_score) 
        VALUES (?, ?, ?)
    ''', (summary_text, content_hash, relevance_score))
    
    conn.commit()
    conn.close()
    print(f"📝 New summary added (relevance: {relevance_score:.2f})")

def get_latest_summary(n: int = 1) -> list[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, summary_text 
        FROM conversation_summaries 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (n,))
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]

# Enhanced Insight functions with deduplication
def add_insight(insight_text: str, category: str = 'general', relevance_score: float = 1.0):
    """Add insight with deduplication, categorization, and freshness guard.

    Freshness guard: if the last 5 insights contain a very similar (>=0.6) one OR
    share same leading 6 words, skip to reduce repetitive mood statements.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    content_hash = generate_content_hash(insight_text)
    
    # Check for exact duplicates
    cursor.execute("SELECT id FROM ai_insights WHERE content_hash = ?", (content_hash,))
    if cursor.fetchone():
        print("🔄 Duplicate insight detected, skipping...")
        conn.close()
        return
    
    # Fetch recent insights for similarity + freshness
    cursor.execute("SELECT insight_text FROM ai_insights ORDER BY timestamp DESC LIMIT 15")
    recent_insights = cursor.fetchall()

    lowered_new = insight_text.lower().strip()
    new_prefix = ' '.join(lowered_new.split()[:6])
    for idx, row in enumerate(recent_insights):
        existing = row[0]
        similarity = calculate_text_similarity(insight_text, existing)
        existing_lower = existing.lower().strip()
        prefix_match = new_prefix and existing_lower.startswith(new_prefix)
        if similarity >= 0.75:
            print(f"🔄 Similar insight detected ({similarity:.2f} similarity), skipping...")
            conn.close(); return
        if idx < 5 and (similarity >= 0.6 or prefix_match):
            print("🔁 Freshness guard: recent similar insight, skipping...")
            conn.close(); return
    
    # Add new insight
    cursor.execute('''
        INSERT INTO ai_insights (insight_text, content_hash, category, relevance_score) 
        VALUES (?, ?, ?, ?)
    ''', (insight_text, content_hash, category, relevance_score))
    
    conn.commit()
    conn.close()
    print(f"💡 New insight added: {category} (relevance: {relevance_score:.2f})")

def get_latest_insights(n: int = 1) -> list[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, insight_text 
        FROM ai_insights 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (n,))
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]

# Initialize database when imported
init_db()

# Memory aging and consolidation functions
def smart_memory_management():
    """Intelligent memory management that preserves important information."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Define core facts that should NEVER be deleted
    core_fact_keywords = ['name', 'age', 'birthday', 'family', 'job', 'profession', 'location', 'city', 'country']
    
    # Only age NON-CORE profile facts and only slightly
    for keyword in core_fact_keywords:
        cursor.execute('''
            UPDATE user_profile 
            SET confidence = CASE 
                WHEN confidence < 1.0 THEN confidence + 0.1 
                ELSE 1.0 
            END
            WHERE key LIKE ? OR value LIKE ?
        ''', (f'%{keyword}%', f'%{keyword}%'))
    
    # Age only LOW-IMPORTANCE summaries (relevance < 0.6)
    cursor.execute('''
        UPDATE conversation_summaries 
        SET relevance_score = relevance_score * 0.95
        WHERE timestamp < datetime('now', '-30 days') 
        AND relevance_score < 0.6
    ''')
    
    # Age only GENERAL insights, preserve specific categories
    cursor.execute('''
        UPDATE ai_insights 
        SET relevance_score = relevance_score * 0.98
        WHERE timestamp < datetime('now', '-30 days') 
        AND category = 'general'
        AND relevance_score < 0.5
    ''')
    
    # Only remove VERY old, VERY low relevance, GENERAL items
    cursor.execute('''
        DELETE FROM conversation_summaries 
        WHERE timestamp < datetime('now', '-180 days') 
        AND relevance_score < 0.1
        AND summary_text NOT LIKE '%name%'
        AND summary_text NOT LIKE '%important%'
    ''')
    
    cursor.execute('''
        DELETE FROM ai_insights 
        WHERE timestamp < datetime('now', '-365 days') 
        AND relevance_score < 0.05
        AND category = 'general'
    ''')
    
    # Log action
    cursor.execute('''
        INSERT INTO memory_consolidation (action, details) 
        VALUES ('smart_management', 'Preserved important memories, aged only low-value items')
    ''')
    
    conn.commit()
    conn.close()
    print("🧠 Smart memory management completed - important memories preserved")

def consolidate_similar_memories():
    """Find and merge very similar memories to reduce redundancy."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all summaries for comparison
    cursor.execute("SELECT id, summary_text, relevance_score FROM conversation_summaries ORDER BY timestamp DESC")
    summaries = cursor.fetchall()
    
    merged_count = 0
    for i, summary1 in enumerate(summaries):
        for j, summary2 in enumerate(summaries[i+1:], i+1):
            similarity = calculate_text_similarity(summary1[1], summary2[1])
            if similarity > 0.85:  # Very similar
                # Keep the one with higher relevance, merge the other
                if summary1[2] >= summary2[2]:
                    keep_id, remove_id = summary1[0], summary2[0]
                else:
                    keep_id, remove_id = summary2[0], summary1[0]
                
                # Update relevance of kept summary
                cursor.execute('''
                    UPDATE conversation_summaries 
                    SET relevance_score = relevance_score + 0.1
                    WHERE id = ?
                ''', (keep_id,))
                
                # Remove duplicate
                cursor.execute("DELETE FROM conversation_summaries WHERE id = ?", (remove_id,))
                merged_count += 1
                break
    
    # Log consolidation
    cursor.execute('''
        INSERT INTO memory_consolidation (action, details) 
        VALUES ('consolidation', ?)
    ''', (f'Merged {merged_count} similar summaries',))
    
    conn.commit()
    conn.close()
    print(f"🧠 Memory consolidation completed: merged {merged_count} similar items")

def get_memory_stats():
    """Get statistics about the memory system."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Count items
    cursor.execute("SELECT COUNT(*) FROM user_profile")
    profile_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM conversation_summaries")
    summary_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ai_insights")
    insight_count = cursor.fetchone()[0]
    
    # Get average relevance scores
    cursor.execute("SELECT AVG(relevance_score) FROM conversation_summaries")
    avg_summary_relevance = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(relevance_score) FROM ai_insights")
    avg_insight_relevance = cursor.fetchone()[0] or 0
    
    # Get recent consolidation actions
    cursor.execute('''
        SELECT action, timestamp FROM memory_consolidation 
        ORDER BY timestamp DESC LIMIT 5
    ''')
    recent_actions = cursor.fetchall()
    
    conn.close()
    
    return {
        'profile_facts': profile_count,
        'summaries': summary_count,
        'insights': insight_count,
        'avg_summary_relevance': round(avg_summary_relevance, 2),
        'avg_insight_relevance': round(avg_insight_relevance, 2),
        'recent_actions': [dict(row) for row in recent_actions]
    }

def get_relevant_summaries(query_keywords: list = None, n: int = 5) -> list[dict]:
    """Get summaries relevant to current conversation context"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if query_keywords:
        # Search for summaries containing keywords
        keyword_conditions = []
        params = []
        for keyword in query_keywords[:3]:  # Limit to 3 keywords
            keyword_conditions.append("summary_text LIKE ?")
            params.append(f"%{keyword.lower()}%")
        
        where_clause = " OR ".join(keyword_conditions)
        query = f"""
            SELECT id, timestamp, summary_text, relevance_score
            FROM conversation_summaries 
            WHERE {where_clause}
            ORDER BY relevance_score DESC, timestamp DESC 
            LIMIT ?
        """
        params.append(n)
        cursor.execute(query, params)
    else:
        # Fallback to high-relevance recent summaries
        cursor.execute("""
            SELECT id, timestamp, summary_text, relevance_score
            FROM conversation_summaries 
            ORDER BY relevance_score DESC, timestamp DESC 
            LIMIT ?
        """, (n,))
    
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]

def get_relevant_insights(query_keywords: list = None, n: int = 8) -> list[dict]:
    """Get insights relevant to current conversation context"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if query_keywords:
        # Search for insights containing keywords
        keyword_conditions = []
        params = []
        for keyword in query_keywords[:3]:  # Limit to 3 keywords
            keyword_conditions.append("insight_text LIKE ?")
            params.append(f"%{keyword.lower()}%")
        
        where_clause = " OR ".join(keyword_conditions)
        query = f"""
            SELECT id, timestamp, insight_text, category, relevance_score
            FROM ai_insights 
            WHERE {where_clause}
            ORDER BY relevance_score DESC, timestamp DESC 
            LIMIT ?
        """
        params.append(n)
        cursor.execute(query, params)
    else:
        # Fallback to high-relevance recent insights
        cursor.execute("""
            SELECT id, timestamp, insight_text, category, relevance_score
            FROM ai_insights 
            ORDER BY relevance_score DESC, timestamp DESC 
            LIMIT ?
        """, (n,))
    
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]

def smart_memory_cleanup():
    """Perform intelligent memory cleanup and consolidation."""
    print("🧠 Starting smart memory cleanup...")
    smart_memory_management()
    consolidate_similar_memories()
    stats = get_memory_stats()
    print(f"🧠 Cleanup complete. Stats: {stats['summaries']} summaries, {stats['insights']} insights, {stats['profile_facts']} profile facts")
    return stats

def clear_all_memory():
    """Clear all memory data from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Clear all tables (using correct table names)
        cursor.execute("DELETE FROM user_profile")
        cursor.execute("DELETE FROM conversation_summaries") 
        cursor.execute("DELETE FROM ai_insights")
        cursor.execute("DELETE FROM memory_consolidation")
        
        conn.commit()
        print("🧹 All memory data cleared successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to clear memory: {e}")
        raise e
    finally:
        conn.close()

# --- Memory Search (for tool integration) ---
def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search across profile facts, recent summaries, and insights.

    Scoring: simple token overlap (#matches / #tokens) with light recency boost for
    summaries & insights (newer = higher). Returns list of dicts:
      { 'type': 'profile'|'summary'|'insight', 'text': str, 'score': float }
    """
    q = (query or '').strip()
    if not q:
        return []
    tokens = [t.lower() for t in q.split() if len(t) > 2]
    if not tokens:
        return []
    token_set = set(tokens)

    conn = get_db_connection()
    cursor = conn.cursor()

    results: list[dict] = []
    # Profile facts
    cursor.execute("SELECT key, value FROM user_profile")
    for key, value in cursor.fetchall():
        blob = f"{key} {value}".lower()
        matches = sum(1 for t in token_set if t in blob)
        if matches:
            score = matches / len(token_set) + 0.2  # small boost for explicit facts
            results.append({'type': 'profile', 'text': f"{key}={value}", 'score': score})

    # Recent summaries
    cursor.execute("SELECT summary_text, timestamp FROM conversation_summaries ORDER BY timestamp DESC LIMIT 50")
    now = datetime.now(timezone.utc)
    for summary_text, ts in cursor.fetchall():
        blob = summary_text.lower()
        matches = sum(1 for t in token_set if t in blob)
        if matches:
            # recency boost (within ~7 days decays)
            try:
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else now
            except Exception:
                dt = now
            age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
            recency = max(0.0, 1.0 - (age_days / 7.0)) * 0.3
            score = matches / len(token_set) + recency
            results.append({'type': 'summary', 'text': summary_text, 'score': score})

    # Recent insights
    cursor.execute("SELECT insight_text, timestamp FROM ai_insights ORDER BY timestamp DESC LIMIT 80")
    for insight_text, ts in cursor.fetchall():
        blob = insight_text.lower()
        matches = sum(1 for t in token_set if t in blob)
        if matches:
            try:
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else now
            except Exception:
                dt = now
            age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
            recency = max(0.0, 1.0 - (age_days / 14.0)) * 0.25
            score = matches / len(token_set) + recency
            results.append({'type': 'insight', 'text': insight_text, 'score': score})

    conn.close()
    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:limit]