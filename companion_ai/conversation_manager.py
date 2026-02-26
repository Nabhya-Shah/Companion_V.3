#!/usr/bin/env python3
"""
Conversation Manager - Handles the new separated architecture
Memory AI processes context BEFORE conversation AI responds

V4: Mem0 integration for automatic memory storage from conversations.
"""

import concurrent.futures
import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple
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
    
    def process_message(self, user_message: str, full_conversation_history: List[Dict] = None, memory_user_id: str | None = None) -> str:
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
        self.memory_context['mem0_user_id'] = effective_mem0_user_id
        ai_response = generate_response(user_message, self.memory_context)
        
        # Step 4: Store conversation exchange for later processing
        self.conversation_history.append({
            "user": user_message,
            "ai": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Step 5: Add to Mem0 immediately (V4 hybrid memory)
        memory_saved = False
        if MEM0_AVAILABLE:
            try:
                messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": ai_response}
                ]
                mem0_add_memory(messages, user_id=effective_mem0_user_id)
                logger.info("Mem0: Stored conversation exchange")
                memory_saved = True
            except Exception as e:
                logger.warning(f"Mem0 storage failed: {e}")
        
        logger.info(f"Conversation exchange stored. Session length: {len(self.conversation_history)}")
        
        return ai_response, memory_saved
    
    def process_message_streaming(self, user_message: str, full_conversation_history: List[Dict] = None, memory_user_id: str | None = None):
        """Streaming version of process_message.
        
        Yields text chunks as they arrive. Stores response after completion.
        Uses orchestrator when USE_ORCHESTRATOR is enabled.
        """
        # Step 1: Update memory context
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
        self.memory_context['mem0_user_id'] = effective_mem0_user_id

        # Step 3: Generate response - use orchestrator if enabled
        full_response = ""
        final_metadata = {}
        
        if core_config.USE_ORCHESTRATOR:
            # V6 Architecture: Use orchestrator for routing
            try:
                import time as _time
                from companion_ai.orchestrator import process_message as orchestrator_process
                from companion_ai.llm_interface import reset_last_request_tokens
                
                # Reset token counter — orchestrator bypasses generate_response()
                reset_last_request_tokens()
                
                _orch_start = _time.time()
                response, metadata = orchestrator_process(user_message, self.memory_context)
                _orch_ms = int((_time.time() - _orch_start) * 1000)
                
                final_metadata = metadata or {}
                final_metadata['orchestrator_ms'] = _orch_ms
                
                # Yield metadata first
                yield {"type": "meta", "data": final_metadata}
                
                # Simulate streaming (orchestrator returns full text)
                for word in response.split(' '):
                    yield word + ' '
                    full_response += word + ' '
                full_response = full_response.strip()
                logger.info(f"Orchestrator completed in {_orch_ms}ms | source={final_metadata.get('source', '?')}")
            except concurrent.futures.TimeoutError:
                logger.error("Orchestrator timed out (120s), falling back to direct")
                final_metadata = {"source": "direct_fallback", "error": "orchestrator_timeout"}
                yield {"type": "meta", "data": final_metadata}
                for chunk in generate_response_streaming(user_message, self.memory_context):
                    full_response += chunk
                    yield chunk
            except Exception as e:
                logger.error(f"Orchestrator failed, falling back: {e}")
                final_metadata = {"source": "direct_fallback", "error": str(e)}
                yield {"type": "meta", "data": final_metadata}
                for chunk in generate_response_streaming(user_message, self.memory_context):
                    full_response += chunk
                    yield chunk
        else:
            final_metadata = {"source": "direct"}
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
        if MEM0_AVAILABLE and not orchestrator_handled_memory:
            import threading
            def _async_mem0_save():
                try:
                    messages = [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": full_response}
                    ]
                    mem0_add_memory(messages, user_id=effective_mem0_user_id)
                    logger.info("Mem0: Stored conversation exchange (async)")
                except Exception as e:
                    logger.warning(f"Mem0 storage failed: {e}")
            
            # Fire-and-forget - don't block the response
            threading.Thread(target=_async_mem0_save, daemon=True).start()
        elif orchestrator_handled_memory:
            logger.info("Mem0: Skipped auto-save (orchestrator memory loop already handled it)")
        
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
