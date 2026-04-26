#!/usr/bin/env python3
"""
Conversation Manager - Handles the new separated architecture
Memory AI processes context BEFORE conversation AI responds

V4: Mem0 integration for automatic memory storage from conversations.
"""

import concurrent.futures
import json
import logging
import re
import requests
from datetime import datetime
from typing import Dict, Iterator, List
from companion_ai.memory.sqlite_backend import (
    get_all_profile_facts, get_relevant_summaries, get_relevant_insights,
    add_summary, upsert_profile_fact, add_insight
)
from companion_ai.llm_interface import generate_response, generate_response_streaming
from companion_ai.memory.ai_processor import (
    analyze_conversation_importance, extract_smart_profile_facts,
    generate_smart_summary, generate_contextual_insight, categorize_insight
)
from companion_ai.core import config as core_config

# Import Mem0 if enabled
if core_config.USE_MEM0:
    try:
        from companion_ai.memory.mem0_backend import add_memory as mem0_add_memory
        MEM0_AVAILABLE = True
    except ImportError:
        MEM0_AVAILABLE = False
else:
    MEM0_AVAILABLE = False

logger = logging.getLogger(__name__)


_LOW_SIGNAL_USER_PATTERNS = (
    "hi", "hey", "hello", "yo", "sup", "what's up", "whats up", "not much",
    "ok", "okay", "k", "thanks", "thank you", "cool", "nice", "lol", "haha",
    "test", "hello?",
)

_MEMORY_DECLARATIVE_PATTERNS = (
    r"\bmy name is\b",
    r"\bi am\b",
    r"\bi'm\b",
    r"\bi live in\b",
    r"\bi work (at|as)\b",
    r"\bmy (favorite|favourite)\b",
    r"\bi (like|prefer|love|hate)\b",
    r"\bremember (this|that)\b",
    r"\bmy (birthday|email|phone|address|timezone)\b",
    r"\bi have (a|an)\b",
)

_LOW_SIGNAL_AI_PATTERNS = (
    "i'm having trouble connecting to my brain",
    "i had trouble processing that",
    "sorry, i'm having trouble responding right now",
    "i'm having connection issues",
)


def _is_memory_worthy_turn(user_message: str, ai_response: str) -> bool:
    """Return True only for turns likely to contain durable user facts/preferences."""
    user = str(user_message or "").strip()
    ai = str(ai_response or "").strip()
    if not user or not ai:
        return False

    user_l = user.lower()
    ai_l = ai.lower()

    # Never learn from fallback/error responses.
    if any(marker in ai_l for marker in _LOW_SIGNAL_AI_PATTERNS):
        return False

    user_words = len(user.split())
    ai_words = len(ai.split())
    normalized_user = re.sub(r"\s+", " ", user_l).strip(" .!?")

    if normalized_user in _LOW_SIGNAL_USER_PATTERNS:
        return False

    has_declarative_signal = any(
        re.search(pattern, user_l) for pattern in _MEMORY_DECLARATIVE_PATTERNS
    )

    # Question-only turns are usually retrieval/action asks, not new facts.
    if "?" in user and not has_declarative_signal:
        return False

    # Filter out short phatic exchanges.
    if user_words <= 5 and ai_words <= 16 and not has_declarative_signal:
        return False

    # Conservative default: only persist likely user profile/preference statements.
    return has_declarative_signal


def _mem0_request_id(trace_id: str | None, stage: str) -> str | None:
    if not trace_id:
        return None
    return f"{trace_id}:{stage}"


def _build_retrieval_stage_events(metadata: Dict) -> List[Dict]:
    """Build retrieval stage lifecycle events from orchestrator metadata."""
    if not isinstance(metadata, dict):
        return []

    loop_result = metadata.get("loop_result") or {}
    loop_meta = loop_result.get("metadata") if isinstance(loop_result, dict) else {}
    retrieval_trace = loop_meta.get("retrieval_trace") if isinstance(loop_meta, dict) else {}
    stages = retrieval_trace.get("stages") if isinstance(retrieval_trace, dict) else None
    if not isinstance(stages, list) or not stages:
        return []

    query = retrieval_trace.get("query")
    default_provider = "internal"
    events: List[Dict] = []
    for idx, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            continue
        stage_name = stage.get("name", "unknown")
        stage_status = stage.get("status", "ok")
        details = stage.get("details") or {}
        provider = details.get("provider") or default_provider
        lifecycle_status = "error" if stage_status == "error" else "done"

        events.append({
            "index": idx,
            "stage": stage_name,
            "name": stage_name,
            "status": "start",
            "duration_ms": 0,
            "meta": {
                "provider": provider,
                "query": query,
            },
        })
        events.append({
            "index": idx,
            "stage": stage_name,
            "name": stage_name,
            "status": lifecycle_status,
            "stage_status": stage_status,
            "duration_ms": int(stage.get("duration_ms", 0) or 0),
            "meta": {
                "provider": provider,
                "query": query,
                "details": details,
            },
        })
    return events


def _is_fast_local_stream_candidate(user_message: str) -> bool:
    """Return True when we can safely bypass orchestrator for casual local chat."""
    try:
        if core_config.get_effective_local_chat_provider() != "local_primary":
            return False
    except Exception:
        return False

    try:
        complexity = core_config.classify_complexity(user_message)
        # Complexity 0 is always safe for direct conversational streaming.
        if complexity == 0:
            return True

        # Allow lightweight complexity-1 prompts when they don't look like
        # explicit tool/memory/task requests.
        if complexity == 1:
            text = str(user_message or "").lower()
            word_count = len(text.split())
            tool_or_memory_markers = (
                "open ", "click", "browser", "tab", "search", "look up",
                "tool", "screen", "vision", "workflow", "schedule", "task",
                "remember", "recall", "save this", "store this",
            )
            if word_count <= 14 and not any(marker in text for marker in tool_or_memory_markers):
                return True

        return False
    except Exception:
        return False


def _build_low_latency_system_prompt(recent_conversation: str) -> str:
    """Build a lightweight prompt for casual local streaming turns.

    We intentionally skip Mem0/brain retrieval in this fast path to reduce
    first-token latency for simple conversational exchanges.
    """
    from companion_ai.core.prompts import get_static_system_prompt_safe

    base = get_static_system_prompt_safe()
    recent = str(recent_conversation or "").strip()
    if not recent:
        return base

    lines = recent.split("\n")
    limited_history = "\n".join(lines[-6:]) if len(lines) > 6 else recent
    return f"{base}\n\nRecent conversation:\n{limited_history}"


def _stream_local_primary_direct(user_message: str, memory_context: Dict) -> Iterator[str]:
    """Stream a direct local response from Ollama for low-complexity chat turns."""
    from companion_ai.llm.ollama_provider import OLLAMA_URL

    model = core_config.get_effective_local_heavy_model()
    recent_conv = memory_context.get("recent_conversation", "")
    system_prompt = _build_low_latency_system_prompt(recent_conv)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": True,
        "think": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
        },
    }

    with requests.post(f"{OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=300) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="ignore").strip()
            else:
                line = str(raw_line or "").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON Ollama stream line")
                continue

            chunk = ((data.get("message") or {}).get("content") or "")
            if chunk:
                yield chunk

# Import knowledge graph (optional - graceful degradation if not available)
try:
    from companion_ai.memory.knowledge_graph import add_conversation_to_graph, get_graph_stats
    KNOWLEDGE_GRAPH_AVAILABLE = True
    logger.info("Knowledge Graph enabled")
except ImportError:
    KNOWLEDGE_GRAPH_AVAILABLE = False
    logger.warning("Knowledge Graph not available - install networkx to enable")

class ConversationSession:
    """Manages a conversation session with separated memory and conversation processing"""
    
    def __init__(self):
        self.conversation_history = []  # Store current session
        self.memory_context = self._load_initial_memory_context()
        
    def _load_initial_memory_context(self) -> Dict:
        """Load initial memory context from database"""
        return {
            "profile": get_all_profile_facts(),
            "summaries": get_relevant_summaries(None, 5),
            "insights": get_relevant_insights(None, 8)
        }
    
    def _update_memory_context_with_keywords(self, user_message: str):
        """Update memory context based on current message keywords"""
        # Extract keywords from user message
        keywords = [word.lower() for word in user_message.split() if len(word) > 3][:3]
        
        # Get relevant memories based on keywords
        if keywords:
            self.memory_context.update({
                "summaries": get_relevant_summaries(keywords, 5),
                "insights": get_relevant_insights(keywords, 8)
            })
            logger.info(f"Updated memory context with keywords: {keywords}")
    
    def process_message(self, user_message: str, full_conversation_history: List[Dict] = None, memory_user_id: str | None = None, trace_id: str | None = None) -> str:
        """
        New conversation flow:
        1. Update memory context with relevant information
        2. Generate response with full context including ALL conversation history
        3. Store conversation for later memory processing
        
        Args:
            user_message: Current user message
            full_conversation_history: Complete conversation history from web session
        """
        
        # Step 1: Update memory context based on current message
        self._update_memory_context_with_keywords(user_message)
        
        # Step 2: Build recent conversation context - LIMIT TO LAST 3 TURNS to save tokens
        if full_conversation_history:
            recent_turns = []
            # Only use last 3 exchanges (6 messages) - older context is in memory summaries
            recent_history = full_conversation_history[-3:]
            for entry in recent_history:
                recent_turns.append(f"User: {entry.get('user', '')}")
                recent_turns.append(f"AI: {entry.get('ai', '')}")
            self.memory_context['recent_conversation'] = "\n".join(recent_turns)
            logger.info(f"Using last {len(recent_history)} of {len(full_conversation_history)} exchanges")
        
        # Step 3: Generate response with enhanced context
        effective_mem0_user_id = memory_user_id or core_config.MEM0_USER_ID
        effective_trace_id = trace_id or self.memory_context.get('trace_id')
        self.memory_context['mem0_user_id'] = effective_mem0_user_id
        if effective_trace_id:
            self.memory_context['trace_id'] = effective_trace_id
        ai_response = generate_response(user_message, self.memory_context)
        
        # Step 4: Store conversation exchange for later processing
        self.conversation_history.append({
            "user": user_message,
            "ai": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Step 5: Add to Mem0 immediately (V4 hybrid memory)
        memory_saved = False
        should_save_memory = _is_memory_worthy_turn(user_message, ai_response)
        if MEM0_AVAILABLE and should_save_memory:
            try:
                messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": ai_response}
                ]
                if effective_trace_id:
                    mem0_result = mem0_add_memory(
                        messages,
                        user_id=effective_mem0_user_id,
                        request_id=_mem0_request_id(effective_trace_id, "chat_sync"),
                    )
                else:
                    mem0_result = mem0_add_memory(messages, user_id=effective_mem0_user_id)
                write_status = (mem0_result or {}).get('write_status', {}) if isinstance(mem0_result, dict) else {}
                status = write_status.get('status')
                memory_saved = status in {'accepted_committed', 'accepted_queued'}
                logger.info(f"Mem0: Stored conversation exchange status={status or 'unknown'}")
            except Exception as e:
                logger.warning(f"Mem0 storage failed: {e}")
        elif MEM0_AVAILABLE and not should_save_memory:
            logger.info("Mem0: Skipped low-signal exchange in sync chat path")
        
        logger.info(f"Conversation exchange stored. Session length: {len(self.conversation_history)}")
        
        return ai_response, memory_saved
    
    def process_message_streaming(self, user_message: str, full_conversation_history: List[Dict] = None, memory_user_id: str | None = None, trace_id: str | None = None):
        """Streaming version of process_message.
        
        Yields text chunks as they arrive. Stores response after completion.
        Uses orchestrator when USE_ORCHESTRATOR is enabled.
        """
        fast_local_stream_candidate = (
            core_config.USE_ORCHESTRATOR and _is_fast_local_stream_candidate(user_message)
        )

        # Step 1: Update memory context (skip for low-latency direct-stream path)
        if not fast_local_stream_candidate:
            self._update_memory_context_with_keywords(user_message)
        
        # Step 2: Build recent conversation context
        if full_conversation_history:
            recent_turns = []
            recent_history = full_conversation_history[-3:]
            for entry in recent_history:
                recent_turns.append(f"User: {entry.get('user', '')}")
                recent_turns.append(f"AI: {entry.get('ai', '')}")
            self.memory_context['recent_conversation'] = "\n".join(recent_turns)
        
        effective_mem0_user_id = memory_user_id or core_config.MEM0_USER_ID
        effective_trace_id = trace_id or self.memory_context.get('trace_id')
        self.memory_context['mem0_user_id'] = effective_mem0_user_id
        if effective_trace_id:
            self.memory_context['trace_id'] = effective_trace_id

        # Step 3: Generate response - use orchestrator if enabled
        full_response = ""
        final_metadata = {}
        used_fast_local_stream = False

        if fast_local_stream_candidate:
            try:
                pending_meta = {
                    "source": "local_streaming_direct",
                    "status": "running",
                    "path": "casual_bypass",
                }
                if effective_trace_id:
                    pending_meta["trace_id"] = effective_trace_id
                yield {"type": "meta", "data": pending_meta}

                for chunk in _stream_local_primary_direct(user_message, self.memory_context):
                    full_response += chunk
                    yield chunk

                final_metadata = {
                    "source": "local_streaming_direct",
                    "path": "casual_bypass",
                }
                if effective_trace_id:
                    final_metadata["trace_id"] = effective_trace_id
                yield {"type": "meta", "data": final_metadata}
                used_fast_local_stream = True
            except Exception as e:
                logger.warning(
                    "Local direct streaming bypass failed; falling back to orchestrator: %s",
                    e,
                )
        
        if core_config.USE_ORCHESTRATOR:
            if not used_fast_local_stream:
                # V6 Architecture: Use orchestrator for routing
                try:
                    import time as _time
                    from companion_ai.orchestration import process_message as orchestrator_process
                    from companion_ai.llm_interface import reset_last_request_tokens

                    # Emit an immediate status event so UI can reflect active processing
                    # while the blocking orchestrator decision executes.
                    pending_meta = {"source": "orchestrator_pending", "status": "running"}
                    if effective_trace_id:
                        pending_meta["trace_id"] = effective_trace_id
                    yield {"type": "meta", "data": pending_meta}

                    # Reset token counter — orchestrator bypasses generate_response()
                    reset_last_request_tokens()

                    _orch_start = _time.time()
                    response, metadata = orchestrator_process(user_message, self.memory_context)
                    _orch_ms = int((_time.time() - _orch_start) * 1000)

                    final_metadata = metadata or {}
                    final_metadata['orchestrator_ms'] = _orch_ms
                    if effective_trace_id:
                        final_metadata['trace_id'] = effective_trace_id

                    # Yield metadata first
                    yield {"type": "meta", "data": final_metadata}

                    # Emit retrieval stages (query_expand/retrieve/rerank/answer) when available.
                    for stage_event in _build_retrieval_stage_events(final_metadata):
                        yield {"type": "retrieval_stage", "data": stage_event}

                    # Simulate streaming (orchestrator returns full text)
                    for word in response.split(' '):
                        yield word + ' '
                        full_response += word + ' '
                    full_response = full_response.strip()
                    logger.info(f"Orchestrator completed in {_orch_ms}ms | source={final_metadata.get('source', '?')}")
                except concurrent.futures.TimeoutError:
                    logger.error("Orchestrator timed out (120s), falling back to direct")
                    final_metadata = {"source": "direct_fallback", "error": "orchestrator_timeout"}
                    if effective_trace_id:
                        final_metadata['trace_id'] = effective_trace_id
                    yield {"type": "meta", "data": final_metadata}
                    for chunk in generate_response_streaming(user_message, self.memory_context):
                        full_response += chunk
                        yield chunk
                except Exception as e:
                    logger.error(f"Orchestrator failed, falling back: {e}")
                    final_metadata = {"source": "direct_fallback", "error": str(e)}
                    if effective_trace_id:
                        final_metadata['trace_id'] = effective_trace_id
                    yield {"type": "meta", "data": final_metadata}
                    for chunk in generate_response_streaming(user_message, self.memory_context):
                        full_response += chunk
                        yield chunk
        else:
            final_metadata = {"source": "direct"}
            if effective_trace_id:
                final_metadata['trace_id'] = effective_trace_id
            yield {"type": "meta", "data": final_metadata}
            for chunk in generate_response_streaming(user_message, self.memory_context):
                full_response += chunk
                yield chunk
        
        # Step 4: Inject token_steps into metadata for UI display
        try:
            from companion_ai.llm_interface import get_last_token_usage
            token_usage = get_last_token_usage()
            final_metadata['token_steps'] = token_usage.get('steps', [])
            final_metadata['total_tokens'] = token_usage.get('total', 0)
            # Yield updated metadata with token info
            yield {"type": "token_meta", "data": final_metadata}
        except Exception as e:
            logger.warning(f"Failed to inject token_steps: {e}")
        
        # Step 5: Store conversation after completion
        self.conversation_history.append({
            "user": user_message,
            "ai": full_response,
            "timestamp": datetime.now().isoformat(),
            "metadata": final_metadata
        })
        
        # Step 6: Add to Mem0 in BACKGROUND (non-blocking for faster UX)
        # Skip if orchestrator already handled memory (avoid duplicate entries)
        orchestrator_handled_memory = final_metadata.get("source", "").startswith("loop_memory")
        should_save_memory = _is_memory_worthy_turn(user_message, full_response)
        self._last_mem0_started = False  # Track whether we actually fired Mem0
        if MEM0_AVAILABLE and not orchestrator_handled_memory and should_save_memory:
            import threading
            self._last_mem0_started = True
            def _async_mem0_save():
                try:
                    messages = [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": full_response}
                    ]
                    if effective_trace_id:
                        mem0_result = mem0_add_memory(
                            messages,
                            user_id=effective_mem0_user_id,
                            request_id=_mem0_request_id(effective_trace_id, "chat_async"),
                        )
                    else:
                        mem0_result = mem0_add_memory(messages, user_id=effective_mem0_user_id)
                    write_status = (mem0_result or {}).get('write_status', {}) if isinstance(mem0_result, dict) else {}
                    logger.info(f"Mem0: Stored conversation exchange (async) status={write_status.get('status', 'unknown')}")
                except Exception as e:
                    logger.warning(f"Mem0 storage failed: {e}")
            
            # Fire-and-forget - don't block the response
            threading.Thread(target=_async_mem0_save, daemon=True).start()
        elif orchestrator_handled_memory:
            self._last_mem0_started = True  # Orchestrator handled it — still a memory save
            logger.info("Mem0: Skipped auto-save (orchestrator memory loop already handled it)")
        elif MEM0_AVAILABLE and not should_save_memory:
            logger.info("Mem0: Skipped low-signal exchange in streaming chat path")
        
        logger.info(f"Streaming complete. Session length: {len(self.conversation_history)}")
    
    def process_session_memory(self):
        """
        Process all conversation memory at end of session
        Uses separate memory API to avoid rate limiting
        """
        if not self.conversation_history:
            logger.info("No conversation history to process")
            return
            
        logger.info(f"Processing memory for {len(self.conversation_history)} exchanges")
        
        # Process each conversation exchange
        for exchange in self.conversation_history:
            try:
                self._process_single_exchange(exchange)
            except Exception as e:
                logger.error(f"Error processing exchange: {e}")
        
        # Clear conversation history after processing
        self.conversation_history.clear()
        logger.info("Session memory processing completed")
    
    def _process_single_exchange(self, exchange: Dict):
        """Process a single conversation exchange for memory storage.

        Uses the canonical ai_processor module for all extraction.
        """
        user_msg = exchange["user"]
        ai_msg = exchange["ai"]

        # Add to knowledge graph if available (visualization only)
        if KNOWLEDGE_GRAPH_AVAILABLE:
            try:
                add_conversation_to_graph(user_msg, ai_msg)
                logger.info("Added to knowledge graph")
            except Exception as e:
                logger.error(f"Knowledge graph processing failed: {e}")

        # Analyze importance
        importance = analyze_conversation_importance(user_msg, ai_msg, {})
        logger.info(f"Exchange importance: {importance:.2f}")

        if importance <= core_config.IMPORTANCE_MIN_STORE:
            logger.info("Low importance exchange - minimal storage")
            return

        # Generate summary
        summary = generate_smart_summary(user_msg, ai_msg, importance)
        if summary:
            add_summary(summary, importance)

        # Extract profile facts (structured with confidence)
        facts = extract_smart_profile_facts(user_msg, ai_msg)
        for key, data in facts.items():
            upsert_profile_fact(
                key,
                data.get('value', ''),
                data.get('confidence', 0.5),
                source='exchange_analysis',
                evidence=data.get('evidence'),
            )

        # Generate insights
        if importance >= core_config.IMPORTANCE_INSIGHT_MIN:
            insight = generate_contextual_insight(user_msg, ai_msg, {}, importance)
            if insight:
                category = categorize_insight(insight)
                add_insight(insight, category, importance)
