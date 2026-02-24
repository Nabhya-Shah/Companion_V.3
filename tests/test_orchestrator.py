"""Tests for the V6 Orchestrator — routing, parsing, fallback, integration."""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# ---------------------------------------------------------------------------
# 1. Decision parsing (OrchestratorDecision.from_json)
# ---------------------------------------------------------------------------

from companion_ai.orchestrator import OrchestratorDecision, OrchestratorAction


class TestDecisionParsing:
    """OrchestratorDecision.from_json must handle every LLM quirk."""

    def test_clean_json_answer(self):
        raw = '{"action": "answer", "content": "Hello!"}'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER
        assert d.content == "Hello!"

    def test_clean_json_delegate_tools(self):
        raw = '{"action": "delegate", "loop": "tools", "task": {"operation": "get_time"}}'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.DELEGATE
        assert d.loop == "tools"
        assert d.task["operation"] == "get_time"

    def test_clean_json_delegate_memory_save(self):
        raw = '{"action": "delegate", "loop": "memory", "task": {"operation": "save", "fact": "User likes cats"}}'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.DELEGATE
        assert d.loop == "memory"
        assert d.task["operation"] == "save"
        assert "cats" in d.task["fact"]

    def test_markdown_wrapped_json(self):
        raw = '```json\n{"action": "answer", "content": "Wrapped!"}\n```'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER
        assert d.content == "Wrapped!"

    def test_generic_code_block_json(self):
        raw = '```\n{"action": "delegate", "loop": "vision", "task": {"operation": "describe"}}\n```'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.DELEGATE
        assert d.loop == "vision"

    def test_truncated_json_regex_fallback(self):
        """LLM sometimes returns truncated JSON — regex extracts content."""
        raw = '{"action": "answer", "content": "I can help with that'  # missing closing } and "
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER
        assert "I can help" in d.content

    def test_plain_text_fallback(self):
        """If 120B returns plain text instead of JSON, use it as content."""
        raw = "Sure, I'd be happy to help with that!"
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER
        assert "happy to help" in d.content

    def test_save_facts_field(self):
        raw = '{"action": "answer", "content": "Got it!", "save_facts": ["User prefers dark mode"]}'
        d = OrchestratorDecision.from_json(raw)
        assert d.save_facts == ["User prefers dark mode"]

    def test_unknown_action_defaults_answer(self):
        raw = '{"action": "unknown_action", "content": "Hmm"}'
        # OrchestratorAction("unknown_action") raises ValueError → regex fallback or error path
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER

    def test_empty_content_answer(self):
        raw = '{"action": "answer"}'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.ANSWER
        assert d.content is None

    def test_memory_search_action(self):
        raw = '{"action": "memory_search", "task": {"query": "what is my name"}}'
        d = OrchestratorDecision.from_json(raw)
        assert d.action == OrchestratorAction.MEMORY_SEARCH


# ---------------------------------------------------------------------------
# 2. Loop registry
# ---------------------------------------------------------------------------

from companion_ai.local_loops import get_loop, list_loops, get_capabilities_summary


class TestLoopRegistry:
    """Verify that the auto-registered loops are discoverable."""

    def test_tools_loop_registered(self):
        loop = get_loop("tools")
        assert loop is not None
        assert loop.name == "tools"

    def test_memory_loop_registered(self):
        loop = get_loop("memory")
        assert loop is not None
        assert loop.name == "memory"

    def test_vision_loop_registered(self):
        loop = get_loop("vision")
        assert loop is not None
        assert loop.name == "vision"

    def test_unknown_loop_returns_none(self):
        assert get_loop("nonexistent_loop") is None

    def test_list_loops_has_three(self):
        loops = list_loops()
        names = {l["name"] for l in loops}
        assert "tools" in names
        assert "memory" in names
        assert "vision" in names

    def test_capabilities_summary_non_empty(self):
        summary = get_capabilities_summary()
        assert "Available local loops:" in summary
        assert "tools" in summary
        assert "memory" in summary

    def test_tools_loop_supported_operations(self):
        loop = get_loop("tools")
        caps = loop.get_capabilities()
        ops = caps["supported_operations"]
        assert "get_time" in ops
        assert "calculate" in ops
        assert "brain_search" in ops
        assert "light_on" in ops

    def test_memory_loop_supported_operations(self):
        loop = get_loop("memory")
        caps = loop.get_capabilities()
        ops = caps["supported_operations"]
        assert "search" in ops
        assert "save" in ops
        assert "extract" in ops
        assert "delete" in ops


# ---------------------------------------------------------------------------
# 3. Orchestrator prompt construction
# ---------------------------------------------------------------------------

from companion_ai.orchestrator import Orchestrator


class TestOrchestratorPrompt:
    """The routing prompt must contain all routing rules."""

    def setup_method(self):
        self.orch = Orchestrator()

    def test_prompt_contains_routing_rules(self):
        prompt = self.orch._build_orchestrator_prompt("hello", {})
        assert "Routing Rules" in prompt
        assert '"action": "answer"' in prompt
        assert '"action": "delegate"' in prompt

    def test_prompt_includes_context_when_provided(self):
        ctx = {"recent_conversation": "User: hi\nAI: hello"}
        prompt = self.orch._build_orchestrator_prompt("how are you", ctx)
        assert "User: hi" in prompt

    def test_prompt_truncates_long_context(self):
        ctx = {"recent_conversation": "x" * 1000}
        prompt = self.orch._build_orchestrator_prompt("test", ctx)
        # The dynamic part should be truncated to 500 chars
        assert len(prompt) < 5000  # Static rules + 500 chars max context

    def test_prompt_has_orpheus_vocal_directions(self):
        prompt = self.orch._build_orchestrator_prompt("test", {})
        assert "Orpheus" in prompt or "TTS" in prompt

    def test_prompt_has_memory_routing(self):
        prompt = self.orch._build_orchestrator_prompt("test", {})
        assert "memory (save)" in prompt
        assert "memory (search)" in prompt

    def test_prompt_has_vision_routing(self):
        prompt = self.orch._build_orchestrator_prompt("test", {})
        assert "vision" in prompt

    def test_prompt_has_loxone_routing(self):
        prompt = self.orch._build_orchestrator_prompt("test", {})
        assert "light_on" in prompt
        assert "light_off" in prompt


# ---------------------------------------------------------------------------
# 4. Orchestrator client fallback
# ---------------------------------------------------------------------------


class TestOrchestratorFallback:
    """When Groq is unreachable, the orchestrator must degrade gracefully."""

    def test_no_client_returns_fallback_decision(self):
        orch = Orchestrator()
        # Force no client
        orch._groq_client = None
        client, model, is_local = orch._get_client_and_model()
        assert client is None
        assert model is None

    def test_get_decision_without_client_returns_answer(self):
        orch = Orchestrator()
        with patch.object(orch, '_get_client_and_model', return_value=(None, None, False)):
            decision = asyncio.run(orch._get_decision("hello", {}))
            assert decision.action == OrchestratorAction.ANSWER
            assert "trouble connecting" in decision.content

    def test_process_with_no_client_returns_error(self):
        orch = Orchestrator()
        with patch.object(orch, '_get_client_and_model', return_value=(None, None, False)):
            response, meta = asyncio.run(orch.process("hello", {}))
            assert "trouble connecting" in response


# ---------------------------------------------------------------------------
# 5. Sync wrapper
# ---------------------------------------------------------------------------

from companion_ai.orchestrator import process_message, get_orchestrator


class TestSyncWrapper:
    """The sync process_message must work from non-async code."""

    def test_sync_wrapper_calls_orchestrator(self):
        """Mock the async internals to verify sync wrapper returns properly."""
        with patch('companion_ai.orchestrator.process_message_async',
                   new_callable=AsyncMock,
                   return_value=("Test response", {"source": "test"})):
            response, meta = process_message("hello")
            assert response == "Test response"
            assert meta["source"] == "test"

    def test_get_orchestrator_singleton(self):
        """get_orchestrator should always return the same instance."""
        o1 = get_orchestrator()
        o2 = get_orchestrator()
        assert o1 is o2


# ---------------------------------------------------------------------------
# 6. Conversation manager orchestrator integration
# ---------------------------------------------------------------------------


class TestConversationManagerIntegration:
    """Test the orchestrator branch of process_message_streaming."""

    def test_orchestrator_path_yields_meta_then_chunks(self, monkeypatch):
        """When orchestrator is ON, the generator should yield meta + text chunks."""
        monkeypatch.setattr('companion_ai.core.config.USE_ORCHESTRATOR', True)

        mock_response = ("Hello from orchestrator!", {"source": "120b_direct"})
        with patch('companion_ai.orchestrator.process_message', return_value=mock_response):
            from companion_ai.conversation_manager import ConversationSession
            session = ConversationSession()

            # Patch out Mem0 to avoid import issues
            monkeypatch.setattr('companion_ai.conversation_manager.MEM0_AVAILABLE', False)

            chunks = list(session.process_message_streaming("hi"))
            
            # First yield should be meta dict
            meta_chunks = [c for c in chunks if isinstance(c, dict) and c.get('type') == 'meta']
            assert len(meta_chunks) >= 1
            assert meta_chunks[0]['data']['source'] == '120b_direct'

            # Remaining yields should be text strings
            text_chunks = [c for c in chunks if isinstance(c, str)]
            full_text = ''.join(text_chunks).strip()
            assert "Hello from orchestrator" in full_text

    def test_fallback_on_orchestrator_error(self, monkeypatch):
        """When orchestrator raises, should fall back to direct streaming."""
        monkeypatch.setattr('companion_ai.core.config.USE_ORCHESTRATOR', True)

        with patch('companion_ai.orchestrator.process_message', side_effect=RuntimeError("Groq down")):
            with patch('companion_ai.conversation_manager.generate_response_streaming',
                       return_value=iter(["Fallback ", "response"])):
                from companion_ai.conversation_manager import ConversationSession
                session = ConversationSession()
                monkeypatch.setattr('companion_ai.conversation_manager.MEM0_AVAILABLE', False)

                chunks = list(session.process_message_streaming("hi"))
                
                meta_chunks = [c for c in chunks if isinstance(c, dict) and c.get('type') == 'meta']
                assert meta_chunks[0]['data']['source'] == 'direct_fallback'
                
                text_chunks = [c for c in chunks if isinstance(c, str)]
                assert "Fallback" in ''.join(text_chunks)

    def test_memory_loop_skips_mem0_autosave(self, monkeypatch):
        """When orchestrator routes to memory loop, Mem0 auto-save should be skipped."""
        monkeypatch.setattr('companion_ai.core.config.USE_ORCHESTRATOR', True)

        mock_response = ("Saved your preference!", {"source": "loop_memory", "loop_result": {}})
        with patch('companion_ai.orchestrator.process_message', return_value=mock_response):
            from companion_ai.conversation_manager import ConversationSession
            session = ConversationSession()
            
            # Enable Mem0 but spy on it
            monkeypatch.setattr('companion_ai.conversation_manager.MEM0_AVAILABLE', True)
            mem0_called = []
            monkeypatch.setattr('companion_ai.conversation_manager.mem0_add_memory',
                                lambda *a, **kw: mem0_called.append(True))

            # Consume generator fully
            list(session.process_message_streaming("I like cats"))
            
            # Give background thread a moment (it shouldn't fire)
            import time
            time.sleep(0.1)
            
            # Mem0 auto-save should NOT have been called
            assert len(mem0_called) == 0

    def test_non_memory_loop_does_mem0_autosave(self, monkeypatch):
        """When orchestrator routes to tools (not memory), Mem0 auto-save should still fire."""
        monkeypatch.setattr('companion_ai.core.config.USE_ORCHESTRATOR', True)

        mock_response = ("It's 3 PM", {"source": "loop_tools", "loop_result": {}})
        with patch('companion_ai.orchestrator.process_message', return_value=mock_response):
            from companion_ai.conversation_manager import ConversationSession
            session = ConversationSession()
            
            monkeypatch.setattr('companion_ai.conversation_manager.MEM0_AVAILABLE', True)
            mem0_called = []
            monkeypatch.setattr('companion_ai.conversation_manager.mem0_add_memory',
                                lambda *a, **kw: mem0_called.append(True))

            list(session.process_message_streaming("what time is it"))
            
            import time
            time.sleep(0.2)
            
            # Mem0 auto-save SHOULD have been called (tools, not memory)
            assert len(mem0_called) >= 1


# ---------------------------------------------------------------------------
# 7. Tool loop execution (unit, no LLM needed)
# ---------------------------------------------------------------------------


class TestToolLoopExecution:
    """Tool loop operations that don't need external services."""

    def test_get_time(self):
        loop = get_loop("tools")
        result = asyncio.run(loop.execute({"operation": "get_time"}))
        assert result.status.value == "success"
        assert "time" in result.data
        assert "date" in result.data

    def test_calculate_simple(self):
        loop = get_loop("tools")
        result = asyncio.run(loop.execute({"operation": "calculate", "expression": "2 + 3"}))
        assert result.status.value == "success"
        assert result.data["result"] == 5

    def test_calculate_invalid_chars(self):
        loop = get_loop("tools")
        result = asyncio.run(loop.execute({"operation": "calculate", "expression": "import os"}))
        assert result.status.value == "error"

    def test_unknown_operation(self):
        loop = get_loop("tools")
        result = asyncio.run(loop.execute({"operation": "nonexistent"}))
        assert result.status.value == "error"


# ---------------------------------------------------------------------------
# 8. Config default
# ---------------------------------------------------------------------------


class TestOrchestratorConfig:
    """Verify the USE_ORCHESTRATOR default is active."""

    def test_orchestrator_enabled_by_default(self):
        from companion_ai.core import config as core_config
        # After P5-B, orchestrator should be ON by default
        assert core_config.USE_ORCHESTRATOR is True
