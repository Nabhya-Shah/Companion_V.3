"""Tests for P5-D Knowledge Unification (D1-D4)."""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# D1 — Auto-index uploads in brain index
# ============================================================================

class TestBrainIndexStorePath:
    """D1: BrainIndex.index_file() supports store_path for uploads."""

    def test_index_file_with_store_path(self, tmp_path):
        """index_file() uses store_path instead of relative_to(BRAIN_BASE) when given."""
        from companion_ai.brain_index import BrainIndex

        # Create a temp file outside BRAIN_BASE
        upload = tmp_path / "doc.txt"
        upload.write_text("This is a long test document with enough text to index. " * 20)

        idx = BrainIndex.__new__(BrainIndex)
        idx._lock = __import__("threading").Lock()

        # Use a temp DB
        db_path = tmp_path / "test_brain.db"
        with patch("companion_ai.brain_index.INDEX_DB", db_path):
            idx._init_db()
            # Mock embedding to avoid Ollama dependency
            idx._get_embedding = MagicMock(return_value=[0.1] * 384)

            chunks = idx.index_file(upload, store_path="uploads/doc.txt")
            assert chunks > 0

            # Verify stored path is "uploads/doc.txt", not a BRAIN_BASE relative path
            with sqlite3.connect(str(db_path)) as conn:
                rows = conn.execute(
                    "SELECT file_path FROM brain_chunks WHERE file_path = 'uploads/doc.txt'"
                ).fetchall()
            assert len(rows) == chunks

    def test_index_file_default_path_uses_brain_base(self, tmp_path):
        """Without store_path, index_file() computes relative from BRAIN_BASE."""
        from companion_ai.brain_index import BrainIndex, BRAIN_BASE

        brain_file = BRAIN_BASE / "test_default.md"
        try:
            brain_file.parent.mkdir(parents=True, exist_ok=True)
            brain_file.write_text("Default path test content. " * 30)

            idx = BrainIndex.__new__(BrainIndex)
            idx._lock = __import__("threading").Lock()

            db_path = tmp_path / "test_brain2.db"
            with patch("companion_ai.brain_index.INDEX_DB", db_path):
                idx._init_db()
                idx._get_embedding = MagicMock(return_value=[0.1] * 384)
                chunks = idx.index_file(brain_file)
                assert chunks > 0

                with sqlite3.connect(str(db_path)) as conn:
                    rows = conn.execute(
                        "SELECT file_path FROM brain_chunks WHERE file_path = 'test_default.md'"
                    ).fetchall()
                assert len(rows) == chunks
        finally:
            if brain_file.exists():
                brain_file.unlink()

    def test_index_file_counts_chunks_without_embeddings(self, tmp_path):
        from companion_ai.brain_index import BrainIndex

        upload = tmp_path / "doc.txt"
        upload.write_text("This is a long test document with enough text to index. " * 20)

        idx = BrainIndex.__new__(BrainIndex)
        idx._lock = __import__("threading").Lock()

        db_path = tmp_path / "test_brain3.db"
        with patch("companion_ai.brain_index.INDEX_DB", db_path):
            idx._init_db()
            idx._get_embedding = MagicMock(return_value=None)

            chunks = idx.index_file(upload, store_path="uploads/doc.txt")
            assert chunks > 0

            with sqlite3.connect(str(db_path)) as conn:
                stored = conn.execute(
                    "SELECT COUNT(*) FROM brain_chunks WHERE file_path = 'uploads/doc.txt'"
                ).fetchone()[0]
                embedded = conn.execute(
                    "SELECT COUNT(*) FROM brain_chunks WHERE file_path = 'uploads/doc.txt' AND embedding IS NOT NULL"
                ).fetchone()[0]

            assert stored == chunks
            assert embedded == 0


# ============================================================================
# D2 — Confidence-based fact system
# ============================================================================

class TestConfidenceFactSystem:
    """D2: Unified confidence model — facts go into user_profile directly."""

    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        """Use a temp SQLite DB for each test."""
        db_path = str(tmp_path / "test_mem.db")
        monkeypatch.setattr(
            "companion_ai.memory.sqlite_backend.get_db_connection",
            lambda: self._connect(db_path),
        )
        self.db_path = db_path
        # Ensure tables exist
        from companion_ai.memory.sqlite_backend import get_db_connection
        conn = get_db_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY, value TEXT, confidence REAL DEFAULT 1.0,
                source TEXT, last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                first_seen_ts TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_ts TEXT, reaffirmations INTEGER DEFAULT 0,
                evidence TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_text TEXT, content_hash TEXT UNIQUE,
                relevance_score REAL DEFAULT 1.0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_text TEXT, category TEXT DEFAULT 'general',
                relevance_score REAL DEFAULT 1.0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_quality_ledger (
                memory_id TEXT PRIMARY KEY, memory_text TEXT,
                user_scope TEXT DEFAULT 'default',
                confidence REAL DEFAULT 0.70,
                confidence_label TEXT,
                reaffirmations INTEGER DEFAULT 0,
                contradiction_state TEXT DEFAULT 'none',
                provenance_source TEXT DEFAULT 'mem0',
                metadata TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_consolidation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT, details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    @staticmethod
    def _connect(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_upsert_new_fact(self):
        from companion_ai.memory.sqlite_backend import upsert_profile_fact, get_all_profile_facts
        upsert_profile_fact("name", "Alice", confidence=0.9)
        facts = get_all_profile_facts()
        assert facts["name"] == "Alice"

    def test_upsert_reaffirm_same_value(self):
        from companion_ai.memory.sqlite_backend import upsert_profile_fact, list_profile_facts_detailed
        upsert_profile_fact("name", "Alice", confidence=0.7)
        upsert_profile_fact("name", "Alice", confidence=0.6)  # same value → reaffirm
        details = list_profile_facts_detailed()
        fact = [d for d in details if d["key"] == "name"][0]
        assert fact["confidence"] > 0.7  # boosted
        assert fact["reaffirmations"] >= 1

    def test_upsert_update_higher_confidence(self):
        from companion_ai.memory.sqlite_backend import upsert_profile_fact, get_all_profile_facts
        upsert_profile_fact("city", "NYC", confidence=0.5)
        upsert_profile_fact("city", "LA", confidence=0.8)  # higher conf → update
        assert get_all_profile_facts()["city"] == "LA"

    def test_upsert_skip_lower_confidence(self):
        from companion_ai.memory.sqlite_backend import upsert_profile_fact, get_all_profile_facts
        upsert_profile_fact("city", "NYC", confidence=0.8)
        upsert_profile_fact("city", "LA", confidence=0.3)  # lower conf → skip
        assert get_all_profile_facts()["city"] == "NYC"

    def test_list_pending_below_threshold(self, monkeypatch):
        from companion_ai.memory.sqlite_backend import upsert_profile_fact, list_pending_profile_facts
        monkeypatch.setattr("companion_ai.core.config.FACT_CONFIDENCE_THRESHOLD", 0.5)
        upsert_profile_fact("hobby", "chess", confidence=0.3)
        upsert_profile_fact("name", "Alice", confidence=0.9)
        pending = list_pending_profile_facts()
        keys = [p["key"] for p in pending]
        assert "hobby" in keys
        assert "name" not in keys

    def test_approve_boosts_confidence(self, monkeypatch):
        from companion_ai.memory.sqlite_backend import (
            upsert_profile_fact, list_pending_profile_facts,
            approve_profile_fact, list_profile_facts_detailed,
        )
        monkeypatch.setattr("companion_ai.core.config.FACT_CONFIDENCE_THRESHOLD", 0.5)
        monkeypatch.setattr("companion_ai.core.config.FACT_AUTO_APPROVE_THRESHOLD", 0.85)
        upsert_profile_fact("pet", "cat", confidence=0.3)
        pending = list_pending_profile_facts()
        assert len(pending) == 1
        pid = pending[0]["id"]
        assert approve_profile_fact(pid)
        details = list_profile_facts_detailed()
        pet = [d for d in details if d["key"] == "pet"][0]
        assert pet["confidence"] >= 0.85

    def test_reject_deletes_fact(self, monkeypatch):
        from companion_ai.memory.sqlite_backend import (
            upsert_profile_fact, list_pending_profile_facts,
            reject_profile_fact, get_all_profile_facts,
        )
        monkeypatch.setattr("companion_ai.core.config.FACT_CONFIDENCE_THRESHOLD", 0.5)
        upsert_profile_fact("bogus", "nonsense", confidence=0.2)
        pending = list_pending_profile_facts()
        pid = pending[0]["id"]
        assert reject_profile_fact(pid)
        assert "bogus" not in get_all_profile_facts()


# ============================================================================
# D3 — Unified knowledge entry point
# ============================================================================

class TestKnowledgeRemember:
    """D3: knowledge.remember() routes to backends."""

    def test_remember_mem0_only(self, monkeypatch):
        from companion_ai.memory.knowledge import remember

        mock_add = MagicMock(return_value={"id": "123"})
        monkeypatch.setattr("companion_ai.core.config.USE_MEM0", True)
        monkeypatch.setattr("companion_ai.memory.mem0_backend.add_memory", mock_add)

        result = remember("User likes coffee", skip_sqlite=True)
        assert result["mem0"] is not None
        mock_add.assert_called_once()

    def test_remember_sqlite_only(self, monkeypatch):
        from companion_ai.memory.knowledge import remember

        mock_upsert = MagicMock()
        monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)
        monkeypatch.setattr("companion_ai.memory.sqlite_backend.upsert_profile_fact", mock_upsert)

        result = remember("User lives in NYC", key="city", skip_mem0=True)
        assert result["sqlite"] is True
        mock_upsert.assert_called_once()

    def test_remember_without_key_skips_sqlite(self, monkeypatch):
        from companion_ai.memory.knowledge import remember

        monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)
        result = remember("Random fact", skip_mem0=True)
        assert result["sqlite"] is False


class TestKnowledgeRecall:
    """D3: knowledge.recall() merges + deduplicates from all backends."""

    def test_recall_merges_sources(self, monkeypatch):
        from companion_ai.memory.knowledge import recall

        monkeypatch.setattr("companion_ai.core.config.USE_MEM0", True)
        monkeypatch.setattr(
            "companion_ai.memory.mem0_backend.search_memories",
            MagicMock(return_value=[
                {"memory": "User is Alice", "score": 0.9, "id": "m1"},
            ]),
        )
        monkeypatch.setattr(
            "companion_ai.memory.sqlite_backend.search_memory",
            MagicMock(return_value=[
                {"text": "name=Alice", "score": 0.8, "type": "profile"},
            ]),
        )
        # Skip brain index (may not be set up in test)
        results = recall("Alice", include_brain=False)
        assert len(results) >= 1
        sources = {r["source"] for r in results}
        assert "mem0" in sources or "profile" in sources

    def test_recall_dedup_removes_near_duplicates(self):
        from companion_ai.memory.knowledge import _dedup_results

        items = [
            {"text": "User likes coffee and tea every morning", "score": 0.9, "source": "mem0"},
            {"text": "User likes coffee and tea every morning too", "score": 0.7, "source": "profile"},
            {"text": "User works at ACME corp", "score": 0.6, "source": "brain"},
        ]
        deduped = _dedup_results(items)
        # The coffee/tea items have >80% token overlap → only the best kept
        assert len(deduped) == 2

    def test_recall_context_formatting(self, monkeypatch):
        from companion_ai.memory.knowledge import recall_context

        monkeypatch.setattr("companion_ai.core.config.USE_MEM0", True)
        monkeypatch.setattr(
            "companion_ai.memory.mem0_backend.search_memories",
            MagicMock(return_value=[
                {"memory": "User is a developer", "score": 0.8, "id": "x"},
            ]),
        )
        monkeypatch.setattr(
            "companion_ai.memory.sqlite_backend.search_memory",
            MagicMock(return_value=[]),
        )
        text = recall_context("developer", include_brain=False)
        assert "[mem0]" in text
        assert "developer" in text


# ============================================================================
# D4 — Filter function from merged extraction
# ============================================================================

class TestFactKeyFilter:
    """D4: _is_valid_fact_key whitelist/blacklist."""

    def test_whitelisted_keys_pass(self):
        from companion_ai.memory.ai_processor import _is_valid_fact_key
        for key in ["name", "favorite_color", "occupation", "hobby", "pet_name", "skill_python"]:
            assert _is_valid_fact_key(key), f"{key} should pass"

    def test_blacklisted_keys_rejected(self):
        from companion_ai.memory.ai_processor import _is_valid_fact_key
        for key in ["user_is_chill", "user_is_quiet", "ai_is_repeating",
                     "conversation_topic", "user_testing"]:
            assert not _is_valid_fact_key(key), f"{key} should be rejected"

    def test_unknown_keys_without_whitelist_match_rejected(self):
        from companion_ai.memory.ai_processor import _is_valid_fact_key
        assert not _is_valid_fact_key("random_thing")
        assert not _is_valid_fact_key("some_metric")


# ============================================================================
# D2 config — missing constants now exist
# ============================================================================

class TestConfigConstants:
    """D2: Verify new config constants exist."""

    def test_importance_insight_min_exists(self):
        from companion_ai.core import config
        assert hasattr(config, "IMPORTANCE_INSIGHT_MIN")
        assert isinstance(config.IMPORTANCE_INSIGHT_MIN, (int, float))

    def test_fact_confidence_threshold_exists(self):
        from companion_ai.core import config
        assert hasattr(config, "FACT_CONFIDENCE_THRESHOLD")
        assert 0 < config.FACT_CONFIDENCE_THRESHOLD < 1

    def test_fact_auto_approve_threshold_exists(self):
        from companion_ai.core import config
        assert hasattr(config, "FACT_AUTO_APPROVE_THRESHOLD")
        assert config.FACT_AUTO_APPROVE_THRESHOLD > config.FACT_CONFIDENCE_THRESHOLD

    def test_enable_fact_approval_exists(self):
        from companion_ai.core import config
        assert hasattr(config, "ENABLE_FACT_APPROVAL")
        assert isinstance(config.ENABLE_FACT_APPROVAL, bool)
