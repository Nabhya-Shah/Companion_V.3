# companion_ai/memory.py
import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone
import hashlib
import logging

logger = logging.getLogger(__name__)

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

    # Pending profile facts (for approval workflow)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_profile_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'conversation',
            suggested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(key, value)
        )
    ''')

    # Sprint C: canonical quality/provenance ledger for vector memories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_quality_ledger (
            memory_id TEXT NOT NULL,
            user_scope TEXT NOT NULL,
            memory_text TEXT NOT NULL,
            confidence REAL DEFAULT 0.70,
            confidence_label TEXT DEFAULT 'medium',
            reaffirmations INTEGER DEFAULT 0,
            contradiction_state TEXT DEFAULT 'none',
            provenance_source TEXT DEFAULT 'mem0',
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_validated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (memory_id, user_scope)
        )
    ''')

    # --- Lightweight schema upgrades (idempotent) ---
    # user_profile extra columns
    for alter in [
        "ALTER TABLE user_profile ADD COLUMN reaffirmations INTEGER DEFAULT 0",
        "ALTER TABLE user_profile ADD COLUMN first_seen_ts TIMESTAMP",
        "ALTER TABLE user_profile ADD COLUMN last_seen_ts TIMESTAMP",
        "ALTER TABLE user_profile ADD COLUMN evidence TEXT"
    ]:
        try:
            cursor.execute(alter)
        except Exception:
            pass
    # pending_profile_facts extra columns
    for alter in [
        "ALTER TABLE pending_profile_facts ADD COLUMN model_conf_label TEXT",
        "ALTER TABLE pending_profile_facts ADD COLUMN justification TEXT",
        "ALTER TABLE pending_profile_facts ADD COLUMN evidence TEXT",
        "ALTER TABLE pending_profile_facts ADD COLUMN status TEXT DEFAULT 'pending'",
        "ALTER TABLE pending_profile_facts ADD COLUMN conflict_with TEXT",
        "ALTER TABLE pending_profile_facts ADD COLUMN reviewed_at TIMESTAMP"
    ]:
        try:
            cursor.execute(alter)
        except Exception:
            pass
    
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


def _to_confidence_label(value: float) -> str:
    if value >= 0.80:
        return 'high'
    if value >= 0.50:
        return 'medium'
    return 'low'


def _safe_float(value: object, default: float = 0.70) -> float:
    try:
        parsed = float(value)
        return max(0.0, min(1.0, parsed))
    except Exception:
        return default


def upsert_memory_quality_entry(
    memory_id: str,
    memory_text: str,
    user_scope: str,
    confidence: float = 0.70,
    reaffirmations: int = 0,
    contradiction_state: str = 'none',
    provenance_source: str = 'mem0',
    metadata: dict | None = None,
) -> bool:
    """Create or update one quality-ledger row for a memory."""
    if not memory_id or not user_scope:
        return False

    confidence = _safe_float(confidence, 0.70)
    confidence_label = _to_confidence_label(confidence)
    metadata_json = json.dumps(metadata or {})

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO memory_quality_ledger (
                memory_id, user_scope, memory_text, confidence, confidence_label,
                reaffirmations, contradiction_state, provenance_source, metadata_json,
                updated_at, last_validated_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(memory_id, user_scope) DO UPDATE SET
                memory_text = excluded.memory_text,
                confidence = excluded.confidence,
                confidence_label = excluded.confidence_label,
                reaffirmations = excluded.reaffirmations,
                contradiction_state = excluded.contradiction_state,
                provenance_source = excluded.provenance_source,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP,
                last_validated_ts = CURRENT_TIMESTAMP
        ''', (
            memory_id,
            user_scope,
            memory_text,
            confidence,
            confidence_label,
            int(reaffirmations or 0),
            contradiction_state or 'none',
            provenance_source or 'mem0',
            metadata_json,
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Failed to upsert memory quality entry {memory_id}: {e}")
        return False
    finally:
        conn.close()


def bulk_sync_memory_quality_from_mem0(memories: list[dict], user_scope: str) -> int:
    """Sync Mem0 records into quality ledger and return number of synced rows."""
    if not memories:
        return 0

    synced = 0
    for item in memories:
        memory_id = item.get('id')
        memory_text = item.get('memory', item.get('text', ''))
        if not memory_id or not memory_text:
            continue

        meta = item.get('metadata') or {}
        confidence = _safe_float(meta.get('confidence', 0.70), 0.70)
        reaffirmations = int(meta.get('reaffirmations', meta.get('frequency', 0)) or 0)
        contradiction_state = (meta.get('contradiction_state') or 'none').strip().lower()
        if contradiction_state not in {'none', 'pending', 'conflict', 'resolved'}:
            contradiction_state = 'none'

        ok = upsert_memory_quality_entry(
            memory_id=memory_id,
            memory_text=memory_text,
            user_scope=user_scope,
            confidence=confidence,
            reaffirmations=reaffirmations,
            contradiction_state=contradiction_state,
            provenance_source='mem0',
            metadata=meta,
        )
        if ok:
            synced += 1

    return synced


def get_memory_quality_map(user_scope: str) -> dict[str, dict]:
    """Return memory_id -> quality metadata map for one scope."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            SELECT memory_id, confidence, confidence_label, reaffirmations,
                   contradiction_state, provenance_source, metadata_json,
                   updated_at, last_validated_ts
            FROM memory_quality_ledger
            WHERE user_scope = ?
        ''', (user_scope,))
        rows = cur.fetchall()
        out: dict[str, dict] = {}
        for row in rows:
            metadata_json = row['metadata_json']
            try:
                metadata = json.loads(metadata_json) if metadata_json else {}
            except Exception:
                metadata = {}
            out[row['memory_id']] = {
                'confidence': row['confidence'],
                'confidence_label': row['confidence_label'],
                'reaffirmations': row['reaffirmations'],
                'contradiction_state': row['contradiction_state'],
                'provenance_source': row['provenance_source'],
                'metadata': metadata,
                'updated_at': row['updated_at'],
                'last_validated_ts': row['last_validated_ts'],
            }
        return out
    finally:
        conn.close()


def delete_memory_quality_entry(memory_id: str, user_scope: str) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM memory_quality_ledger WHERE memory_id = ? AND user_scope = ?",
            (memory_id, user_scope),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to delete memory quality entry {memory_id}: {e}")
        return False
    finally:
        conn.close()


def rank_memories_by_quality(memories: list[dict], user_scope: str, query: str | None = None) -> list[dict]:
    """Rank memory hits using quality-ledger signals + lexical overlap.

    Returned rows keep original fields and include:
      - quality_confidence
      - quality_confidence_label
      - quality_contradiction_state
      - score (overridden blended score)
    """
    if not memories:
        return []

    q_tokens = {t.lower() for t in (query or '').split() if len(t) > 2}
    quality_map = get_memory_quality_map(user_scope)
    ranked: list[dict] = []

    for item in memories:
        row = dict(item)
        memory_id = row.get('id')
        text = row.get('memory', row.get('text', ''))
        text_lower = str(text).lower()
        base_score = _safe_float(row.get('score', 0.0), 0.0)

        quality = quality_map.get(memory_id, {}) if memory_id else {}
        confidence = _safe_float(quality.get('confidence', 0.70), 0.70)
        contradiction_state = quality.get('contradiction_state', 'none') or 'none'
        contradiction_state = contradiction_state.lower()

        overlap = 0.0
        if q_tokens:
            matches = sum(1 for token in q_tokens if token in text_lower)
            overlap = matches / len(q_tokens)

        contradiction_penalty = 0.0
        if contradiction_state == 'conflict':
            contradiction_penalty = 1.0
        elif contradiction_state == 'pending':
            contradiction_penalty = 0.2

        blended = base_score + (confidence * 0.60) + (overlap * 0.50) - contradiction_penalty

        row['score'] = round(blended, 4)
        row['quality_confidence'] = confidence
        row['quality_confidence_label'] = quality.get('confidence_label', _to_confidence_label(confidence))
        row['quality_contradiction_state'] = contradiction_state
        ranked.append(row)

    ranked.sort(key=lambda x: x.get('score', 0), reverse=True)
    return ranked

# Enhanced Profile functions
def upsert_profile_fact(key: str, value: str, confidence: float = 1.0, source: str = 'conversation', evidence: str | None = None,
                        model_conf_label: str | None = None, justification: str | None = None):
    """Insert or update profile fact.

    Extended behaviors:
      - If approval workflow enabled, optionally stage unless auto-approve threshold met.
      - If fact exists with SAME value -> reaffirm (boost confidence, increment reaffirmations, update last_seen_ts).
      - If fact exists with DIFFERENT value -> stage as proposed update (conflict) unless high-confidence override.
    """
    from companion_ai.core import config as core_config
    # Optional second-pass verification (pre-staging) for low-confidence facts
    try:
        if getattr(core_config, 'VERIFY_FACTS_SECOND_PASS', False) and confidence < 0.75:
            # Lightweight guard to avoid repeated verification loops
            from companion_ai.llm_interface import generate_model_response
            verifier_model = getattr(core_config, 'PRIMARY_MODEL', core_config.DEFAULT_CONVERSATION_MODEL)
            prompt = (
                f"Evaluate the truthfulness and specificity of this proposed user fact.\n"
                f"Fact: {key} = {value}\n"
                "Return STRICT JSON: {\"verdict\": \"accept\"|\"uncertain\"|\"reject\", \"reason\": str, \"suggest_confidence\": 0.0-1.0}." )
            try:
                raw = generate_model_response(prompt, "You are a JSON fact verifier.", verifier_model)
                import re, json as _json
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if m:
                    parsed = _json.loads(m.group())
                    verdict = parsed.get('verdict','uncertain')
                    suggest_conf = float(parsed.get('suggest_confidence', confidence)) if isinstance(parsed.get('suggest_confidence'), (int,float,str)) else confidence
                    suggest_conf = max(0.0, min(1.0, suggest_conf))
                    if verdict == 'reject':
                        print(f"❌ Fact rejected by verifier: {key}={value} reason={parsed.get('reason')}")
                        return  # drop silently
                    if verdict == 'uncertain':
                        # keep but cap confidence
                        confidence = min(confidence, suggest_conf, 0.55)
                    elif verdict == 'accept':
                        confidence = max(confidence, suggest_conf)
                    justification = (justification or '') + f" [verifier: {verdict} {parsed.get('reason','')[:120]}]"
            except Exception as ve:
                print(f"Verifier error (continuing): {ve}")
    except Exception:
        pass

    if getattr(core_config, 'ENABLE_FACT_APPROVAL', False):
        auto = getattr(core_config, 'FACT_AUTO_APPROVE', False) and confidence >= getattr(core_config, 'FACT_AUTO_APPROVE_MIN_CONF', 0.85)
        # Check existing current value to detect conflict early
        conn_chk = get_db_connection(); cur_chk = conn_chk.cursor()
        try:
            cur_chk.execute("SELECT value, confidence FROM user_profile WHERE key = ?", (key,))
            row = cur_chk.fetchone()
        finally:
            conn_chk.close()
        if row and row[0] != value and not auto:
            # Stage as conflict update proposal
            conn = get_db_connection(); cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO pending_profile_facts (key, value, confidence, source, model_conf_label, justification, evidence, status, conflict_with)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed_update', ?)
                ''', (key, value, confidence, source, model_conf_label, justification, evidence, row[0]))
                conn.commit()
                print(f"⚠️ Conflict staged: {key} existing={row[0]} new={value} ({confidence:.2f})")
            finally:
                conn.close()
            return
        if not auto:
            # Stage into pending table instead of immediate commit
            conn = get_db_connection(); cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO pending_profile_facts (key, value, confidence, source, model_conf_label, justification, evidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (key, value, confidence, source, model_conf_label, justification, evidence))
                conn.commit()
                print(f"🕒 Staged profile fact for approval: {key}={value} ({confidence:.2f})")
            finally:
                conn.close()
            return
        print(f"✅ Auto-approved fact (confidence {confidence:.2f}): {key}={value}")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if key exists and compare values
    cursor.execute("SELECT value, confidence FROM user_profile WHERE key = ?", (key,))
    existing = cursor.fetchone()
    
    if existing:
        existing_value, existing_confidence = existing
        if existing_value == value:
            # Reaffirmation path
            new_conf = round(existing_confidence + 0.1 * (1 - existing_confidence), 4)
            cursor.execute('''
                UPDATE user_profile
                SET confidence = ?, reaffirmations = COALESCE(reaffirmations,0)+1, last_updated = CURRENT_TIMESTAMP,
                    last_seen_ts = CURRENT_TIMESTAMP
                WHERE key = ?
            ''', (new_conf, key))
            print(f"🔁 Reaffirmed profile fact: {key}={value} (confidence {existing_confidence:.2f}→{new_conf:.2f})")
        else:
            # Different value (should have been staged if approval on); treat as update override.
            cursor.execute('''
                UPDATE user_profile
                SET value = ?, confidence = ?, last_updated = CURRENT_TIMESTAMP, source = ?, last_seen_ts = CURRENT_TIMESTAMP
                WHERE key = ?
            ''', (value, confidence, source, key))
            print(f"📝 Updated profile (override): {key} = {value} (confidence: {confidence:.2f})")
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

def update_profile_fact(key: str, value: str) -> bool:
    """Compatibility helper for legacy update callers.

    Uses upsert semantics and returns True on success.
    """
    try:
        upsert_profile_fact(key, value)
        return True
    except Exception as e:
        logger.error(f"Failed to update profile fact {key}: {e}")
        return False

def list_profile_facts_detailed(limit: int | None = None) -> list[dict]:
    """Return full provenance metadata for profile facts.

    Fields returned:
      key, value, confidence, reaffirmations, source, last_updated,
      first_seen_ts, last_seen_ts, evidence, confidence_label

    confidence_label derived:
      >=0.80 -> high
      >=0.50 -> medium
      else  -> low
    """
    conn = get_db_connection(); cur = conn.cursor()
    try:
        q = ("SELECT key, value, confidence, COALESCE(reaffirmations,0) AS reaffirmations, "
             "source, last_updated, first_seen_ts, last_seen_ts, evidence FROM user_profile "
             "ORDER BY last_updated DESC")
        if limit:
            q += " LIMIT ?"; cur.execute(q, (limit,))
        else:
            cur.execute(q)
        rows = cur.fetchall()
        out: list[dict] = []
        for r in rows:
            conf = r['confidence'] if isinstance(r['confidence'], (int,float)) else 0.0
            if conf >= 0.80:
                label = 'high'
            elif conf >= 0.50:
                label = 'medium'
            else:
                label = 'low'
            out.append({
                'key': r['key'],
                'value': r['value'],
                'confidence': round(conf,4),
                'confidence_label': label,
                'reaffirmations': r['reaffirmations'],
                'source': r['source'],
                'last_updated': r['last_updated'],
                'first_seen_ts': r['first_seen_ts'],
                'last_seen_ts': r['last_seen_ts'],
                'evidence': r['evidence']
            })
        return out
    finally:
        conn.close()

def delete_profile_fact(key: str) -> bool:
    """Delete a profile fact by key. Returns True if deleted."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_profile WHERE key = ?", (key,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted profile fact: {key}")
        return deleted
    finally:
        conn.close()

def list_pending_profile_facts() -> list[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, key, value, confidence, source, suggested_at, status, conflict_with,
               model_conf_label, justification, evidence
        FROM pending_profile_facts
        WHERE status IN ('pending', 'proposed_update') OR status IS NULL
        ORDER BY suggested_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stale_profile_facts(limit: int = 3) -> list[dict]:
    """Return older facts with low reaffirmations to gently reaffirm in prompts.

    Heuristic: order by (reaffirmations ASC, last_seen_ts/last_updated oldest) and limit.
    """
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute('''
            SELECT key, value, confidence, COALESCE(reaffirmations,0) as reaf,
                   COALESCE(last_seen_ts,last_updated, first_seen_ts) as last_ts
            FROM user_profile
            ORDER BY reaf ASC, last_ts ASC
            LIMIT ?
        ''', (limit,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()

def approve_profile_fact(pending_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value, confidence, source, status FROM pending_profile_facts WHERE id = ?", (pending_id,))
    row = cursor.fetchone()
    if not row:
        conn.close(); return False
    key, value, confidence, source, status = row
    if status in ('approved', 'rejected'):
        conn.close(); return False
    conn.close()
    # Use normal upsert (will bypass staging if feature still enabled because of recursion guard)
    from companion_ai.core import config as core_config
    # Temporarily disable staging to commit
    original = getattr(core_config, 'ENABLE_FACT_APPROVAL', False)
    setattr(core_config, 'ENABLE_FACT_APPROVAL', False)
    try:
        upsert_profile_fact(key, value, confidence, source)
    finally:
        setattr(core_config, 'ENABLE_FACT_APPROVAL', original)
    # Mark approved (retain provenance trail)
    conn2 = get_db_connection(); cur2 = conn2.cursor()
    cur2.execute(
        "UPDATE pending_profile_facts SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (pending_id,)
    )
    conn2.commit(); conn2.close()
    return True

def reject_profile_fact(pending_id: int) -> bool:
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(
        "UPDATE pending_profile_facts SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP WHERE id = ? AND status NOT IN ('approved', 'rejected')",
        (pending_id,)
    )
    changed = cur.rowcount > 0
    conn.commit(); conn.close(); return changed

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

def get_profile_fact(key: str) -> str | None:
    """Get the value of a specific profile fact by key."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

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

# --- Confidence Decay & Reaffirmation Scheduler Helpers ---
def decay_profile_confidence(rate: float = 0.005, floor: float = 0.2):
    """Apply a tiny decay to confidence for facts not seen recently.

    This motivates reaffirmation; core facts are protected by smart_management.
    """
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute('''
            UPDATE user_profile
            SET confidence = MAX(?, confidence - ?)
            WHERE (last_seen_ts IS NULL OR last_seen_ts < datetime('now','-7 days'))
        ''', (floor, rate))
        conn.commit()
    finally:
        conn.close()

def touch_stale_facts(limit: int = 3):
    """Mark a few stale facts as recently considered to surface in prompts."""
    stale = get_stale_profile_facts(limit)
    if not stale:
        return 0
    conn = get_db_connection(); cur = conn.cursor(); n=0
    try:
        for row in stale:
            cur.execute('UPDATE user_profile SET last_seen_ts = CURRENT_TIMESTAMP WHERE key = ?', (row['key'],))
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()

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
        cursor.execute("DELETE FROM memory_quality_ledger")
        
        conn.commit()
        print("[OK] All memory data cleared successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to clear memory: {e}")
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
                # Ensure timezone awareness
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
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
                # Ensure timezone awareness
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = now
            age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
            recency = max(0.0, 1.0 - (age_days / 14.0)) * 0.25
            score = matches / len(token_set) + recency
            results.append({'type': 'insight', 'text': insight_text, 'score': score})

    conn.close()
    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:limit]