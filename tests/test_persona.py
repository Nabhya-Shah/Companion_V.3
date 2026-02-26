# tests/test_persona.py
"""Tests for the persona evolution system (P5-E)."""

import os
import tempfile
import threading
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Patch TRAITS_FILE before importing persona so all disk I/O goes to a tmpdir
# ---------------------------------------------------------------------------

_tmp = tempfile.mkdtemp()
_tmp_traits = os.path.join(_tmp, "learned_traits.yaml")

import companion_ai.services.persona as persona

persona.TRAITS_FILE = _tmp_traits


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset singleton state + traits file between tests."""
    persona.reset_state()
    if os.path.exists(_tmp_traits):
        os.remove(_tmp_traits)
    yield
    persona.reset_state()


# ======================================================================
# PersonaState basics
# ======================================================================

class TestPersonaState:
    def test_default_state(self):
        st = persona.PersonaState()
        assert st.rapport_level == "Stranger"
        assert st.interaction_count == 0
        assert st.evolved_traits == []
        assert st.user_style == []

    def test_round_trip(self):
        st = persona.PersonaState(
            user_style=["casual", "brief"],
            evolved_traits=["witty", "sarcastic"],
            rapport_level="Comfortable",
            interaction_count=99,
        )
        d = st.to_dict()
        st2 = persona.PersonaState.from_dict(d)
        assert st2.user_style == st.user_style
        assert st2.evolved_traits == st.evolved_traits
        assert st2.rapport_level == st.rapport_level
        assert st2.interaction_count == st.interaction_count

    def test_prompt_fragment_content(self):
        st = persona.PersonaState(
            evolved_traits=["direct", "humorous"],
            user_style=["technical", "brief"],
            rapport_level="Familiar",
        )
        frag = st.prompt_fragment()
        assert "[Adaptive Personality Traits]" in frag
        assert "direct" in frag
        assert "[User Communication Style]" in frag
        assert "technical" in frag
        assert "[Rapport Level]: Familiar" in frag

    def test_prompt_fragment_empty(self):
        st = persona.PersonaState()
        frag = st.prompt_fragment()
        # Only rapport line should appear (rapport defaults to "Stranger")
        assert "Stranger" in frag
        assert "Personality Traits" not in frag


# ======================================================================
# Rapport progression
# ======================================================================

class TestRapport:
    @pytest.mark.parametrize("count,expected", [
        (0, "Stranger"),
        (5, "Stranger"),
        (10, "Stranger"),
        (11, "Acquaintance"),
        (30, "Acquaintance"),
        (31, "Familiar"),
        (80, "Familiar"),
        (81, "Comfortable"),
        (200, "Comfortable"),
        (201, "Close"),
        (999, "Close"),
    ])
    def test_rapport_for_count(self, count, expected):
        assert persona._rapport_for_count(count) == expected


# ======================================================================
# Trait merging
# ======================================================================

class TestTraitMerging:
    def test_dedup_case_insensitive(self):
        existing = ["Witty", "Direct"]
        incoming = ["witty", "New Trait"]
        result = persona._merge_list(existing, incoming, cap=10)
        assert len(result) == 3
        assert "New Trait" in result

    def test_cap_applied(self):
        existing = ["a", "b", "c"]
        incoming = ["d", "e"]
        result = persona._merge_list(existing, incoming, cap=4)
        assert len(result) == 4
        # Should keep the most recent
        assert "e" in result

    def test_empty_incoming(self):
        existing = ["a", "b"]
        result = persona._merge_list(existing, [], cap=10)
        assert result == ["a", "b"]


# ======================================================================
# record_interaction
# ======================================================================

class TestRecordInteraction:
    def test_increments_count(self):
        st = persona.get_state()
        assert st.interaction_count == 0
        persona.record_interaction()
        assert st.interaction_count == 1

    def test_updates_rapport(self):
        st = persona.get_state()
        for _ in range(11):
            persona.record_interaction()
        assert st.rapport_level == "Acquaintance"

    def test_returns_true_at_threshold(self):
        st = persona.get_state()
        # Manually set count just below threshold
        st.interaction_count = persona.EVOLVE_EVERY_N_MESSAGES - 1
        result = persona.record_interaction()
        assert result is True

    def test_returns_false_normally(self):
        result = persona.record_interaction()
        assert result is False


# ======================================================================
# on_memory_event
# ======================================================================

class TestOnMemoryEvent:
    def test_low_importance_ignored(self):
        persona.on_memory_event("some fact", importance=0.3)
        st = persona.get_state()
        assert len(st.evolved_traits) == 0

    def test_high_importance_adds_trait(self):
        persona.on_memory_event("User is a software engineer", importance=0.8)
        st = persona.get_state()
        assert len(st.evolved_traits) == 1
        assert "software engineer" in st.evolved_traits[0].lower()

    def test_duplicate_skipped(self):
        persona.on_memory_event("User likes Python", importance=0.9)
        persona.on_memory_event("User likes Python", importance=0.9)
        st = persona.get_state()
        assert len(st.evolved_traits) == 1


# ======================================================================
# _apply_evolution
# ======================================================================

class TestApplyEvolution:
    def test_merges_incrementally(self):
        st = persona.get_state()
        st.evolved_traits = ["existing_trait"]

        persona._apply_evolution({
            "evolved_traits": ["new_trait"],
            "user_style": ["concise"],
            "rapport_level": "Familiar",
        })

        assert "existing_trait" in st.evolved_traits
        assert "new_trait" in st.evolved_traits
        assert "concise" in st.user_style
        assert st.rapport_level == "Familiar"

    def test_creates_history_snapshot(self):
        st = persona.get_state()
        st.evolved_traits = ["old"]

        persona._apply_evolution({"evolved_traits": ["new"]})

        assert len(st.trait_history) == 1
        assert "old" in st.trait_history[0]["evolved_traits"]

    def test_unknown_rapport_falls_back_to_count(self):
        st = persona.get_state()
        st.interaction_count = 50  # should be "Familiar"

        persona._apply_evolution({"rapport_level": "Best Buddies"})

        assert st.rapport_level == "Familiar"


# ======================================================================
# Persistence
# ======================================================================

class TestPersistence:
    def test_save_and_reload(self):
        st = persona.get_state()
        st.evolved_traits = ["persistent_trait"]
        st.interaction_count = 42
        persona.persist_state()

        # Reset singleton, force reload
        persona.reset_state()
        st2 = persona.get_state()
        assert "persistent_trait" in st2.evolved_traits
        assert st2.interaction_count == 42

    def test_ensure_traits_file_creates_default(self):
        assert not os.path.exists(_tmp_traits)
        persona.ensure_traits_file()
        assert os.path.exists(_tmp_traits)


# ======================================================================
# analyze_and_evolve (mocked LLM)
# ======================================================================

class TestAnalyzeAndEvolve:
    def test_empty_history_noop(self):
        persona.analyze_and_evolve([])
        st = persona.get_state()
        assert st.evolved_traits == []

    @patch("companion_ai.llm_interface.generate_model_response")
    def test_successful_evolution(self, mock_gen):
        mock_gen.return_value = '{"user_style": ["techy"], "evolved_traits": ["patient"], "rapport_level": "Familiar"}'

        history = [{"user": "Hello", "ai": "Hey there!"}]
        persona.analyze_and_evolve(history)

        st = persona.get_state()
        assert "patient" in st.evolved_traits
        assert "techy" in st.user_style

    @patch("companion_ai.llm_interface.generate_model_response")
    def test_malformed_json_handled(self, mock_gen):
        mock_gen.return_value = "This is not JSON at all"

        history = [{"user": "hi", "ai": "hey"}]
        persona.analyze_and_evolve(history)

        st = persona.get_state()
        assert st.evolved_traits == []  # nothing changed


# ======================================================================
# Integration: context_builder uses PersonaState
# ======================================================================

class TestContextBuilderIntegration:
    def test_dynamic_traits_uses_persona_state(self):
        """_load_dynamic_traits should return the PersonaState prompt fragment."""
        st = persona.get_state()
        st.evolved_traits = ["friendly", "concise"]
        st.rapport_level = "Comfortable"

        from companion_ai.core.context_builder import _load_dynamic_traits
        result = _load_dynamic_traits()
        assert "friendly" in result
        assert "concise" in result
        assert "Comfortable" in result
