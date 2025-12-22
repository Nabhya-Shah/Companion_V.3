#!/usr/bin/env python3
"""
Conversation Manager - Handles the new separated architecture
Memory AI processes context BEFORE conversation AI responds

V4: Mem0 integration for automatic memory storage from conversations.
"""

import logging
import re
from typing import Dict, List, Tuple
from companion_ai import memory as db
from companion_ai.llm_interface import generate_response, generate_response_streaming, groq_memory_client
from companion_ai.memory_ai import analyze_conversation_importance, extract_smart_profile_facts, generate_smart_summary, generate_contextual_insight, categorize_insight
from companion_ai.core import config as core_config
from companion_ai import persona_evolution

# Import Mem0 if enabled
if core_config.USE_MEM0:
    try:
        from companion_ai.memory_v2 import add_memory as mem0_add_memory
        MEM0_AVAILABLE = True
    except ImportError:
        MEM0_AVAILABLE = False
else:
    MEM0_AVAILABLE = False

logger = logging.getLogger(__name__)

# Import knowledge graph (optional - graceful degradation if not available)
try:
    from companion_ai.memory_graph import add_conversation_to_graph, get_graph_stats
    KNOWLEDGE_GRAPH_AVAILABLE = True
    logger.info("✅ Knowledge Graph enabled")
except ImportError:
    KNOWLEDGE_GRAPH_AVAILABLE = False
    logger.warning("⚠️ Knowledge Graph not available - install networkx to enable")

class ConversationSession:
    """Manages a conversation session with separated memory and conversation processing"""
    
    def __init__(self):
        self.conversation_history = []  # Store current session
        self.memory_context = self._load_initial_memory_context()
        
    def _load_initial_memory_context(self) -> Dict:
        """Load initial memory context from database"""
        return {
            "profile": db.get_all_profile_facts(),
            "summaries": db.get_relevant_summaries(None, 5),
            "insights": db.get_relevant_insights(None, 8)
        }
    
    def _update_memory_context_with_keywords(self, user_message: str):
        """Update memory context based on current message keywords"""
        # Extract keywords from user message
        keywords = [word.lower() for word in user_message.split() if len(word) > 3][:3]
        
        # Get relevant memories based on keywords
        if keywords:
            self.memory_context.update({
                "summaries": db.get_relevant_summaries(keywords, 5),
                "insights": db.get_relevant_insights(keywords, 8)
            })
            logger.info(f"Updated memory context with keywords: {keywords}")
    
    def process_message(self, user_message: str, full_conversation_history: List[Dict] = None) -> str:
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
        ai_response = generate_response(user_message, self.memory_context)
        
        # Step 4: Store conversation exchange for later processing
        self.conversation_history.append({
            "user": user_message,
            "ai": ai_response,
            "timestamp": db.datetime.now().isoformat()
        })
        
        # Step 5: Add to Mem0 immediately (V4 hybrid memory)
        memory_saved = False
        if MEM0_AVAILABLE:
            try:
                messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": ai_response}
                ]
                mem0_add_memory(messages, user_id=core_config.MEM0_USER_ID)
                logger.info("📝 Mem0: Stored conversation exchange")
                memory_saved = True
            except Exception as e:
                logger.warning(f"Mem0 storage failed: {e}")
        
        logger.info(f"Conversation exchange stored. Session length: {len(self.conversation_history)}")
        
        return ai_response, memory_saved
    
    def process_message_streaming(self, user_message: str, full_conversation_history: List[Dict] = None):
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
        
        # Step 3: Generate response - use orchestrator if enabled
        full_response = ""
        
        if core_config.USE_ORCHESTRATOR:
            # V6 Architecture: Use orchestrator for routing
            try:
                from companion_ai.orchestrator import process_message as orchestrator_process
                response, metadata = orchestrator_process(user_message, self.memory_context)
                # Simulate streaming by yielding word by word
                for word in response.split(' '):
                    yield word + ' '
                    full_response += word + ' '
                full_response = full_response.strip()
                logger.info(f"Orchestrator metadata: {metadata}")
            except Exception as e:
                logger.error(f"Orchestrator failed, falling back: {e}")
                # Fallback to normal streaming
                for chunk in generate_response_streaming(user_message, self.memory_context):
                    full_response += chunk
                    yield chunk
        else:
            # Standard streaming
            for chunk in generate_response_streaming(user_message, self.memory_context):
                full_response += chunk
                yield chunk
        
        # Step 4: Store conversation after completion
        self.conversation_history.append({
            "user": user_message,
            "ai": full_response,
            "timestamp": db.datetime.now().isoformat()
        })
        
        # Step 5: Add to Mem0 immediately (V4 hybrid memory)
        if MEM0_AVAILABLE:
            try:
                messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": full_response}
                ]
                mem0_add_memory(messages, user_id=core_config.MEM0_USER_ID)
                logger.info("📝 Mem0: Stored conversation exchange (streaming)")
            except Exception as e:
                logger.warning(f"Mem0 storage failed: {e}")
        
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
        """Process a single conversation exchange for memory storage"""
        user_msg = exchange["user"]
        ai_msg = exchange["ai"]
        
        # Use memory client for processing
        if not groq_memory_client:
            logger.warning("Memory client not available, skipping memory processing")
            return
        
        # Add to knowledge graph if available
        if KNOWLEDGE_GRAPH_AVAILABLE:
            try:
                add_conversation_to_graph(user_msg, ai_msg)
                logger.info("📊 Added to knowledge graph")
            except Exception as e:
                logger.error(f"Knowledge graph processing failed: {e}")
        
        # Analyze importance using memory AI
        importance = self._analyze_importance_with_memory_ai(user_msg, ai_msg)
        logger.info(f"🧠 Exchange importance: {importance:.2f}")
        if importance > core_config.IMPORTANCE_MIN_STORE:  # Store if moderately important
            # Generate summary
            summary = self._generate_summary_with_memory_ai(user_msg, ai_msg, importance)
            if summary:
                db.add_summary(summary, importance)

            # Extract profile facts (structured)
            facts = self._extract_facts_with_memory_ai(user_msg, ai_msg)
            for key, data in facts.items():
                db.upsert_profile_fact(
                    key,
                    data.get('value',''),
                    data.get('confidence',0.5),
                    source='exchange_analysis',
                    evidence=data.get('evidence'),
                    model_conf_label=data.get('conf_label'),
                    justification=data.get('justification')
                )

            # Generate insights
            insight = self._generate_insight_with_memory_ai(user_msg, ai_msg, importance)
            if insight:
                category = self._categorize_insight_with_memory_ai(insight)
                db.add_insight(insight, category, importance)
        else:
            logger.info("🧠 Low importance exchange - minimal storage")
    
    def _analyze_importance_with_memory_ai(self, user_msg: str, ai_msg: str) -> float:
        """Analyze conversation importance using dedicated memory AI"""
        prompt = f"""Rate this conversation's importance for long-term memory (0.0-1.0):

CRITERIA:
- Personal info revealed (0.7-1.0)
- Emotional significance (0.6-0.9)
- Preferences/insights (0.5-0.8)
- Technical discussion (0.4-0.7)
- Casual chat (0.1-0.3)

User: {user_msg}
AI: {ai_msg}

Return only the decimal score:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",  # Scout for quality
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50
            )
            
            # Extract score
            import re
            score_text = response.choices[0].message.content.strip()
            match = re.search(r'(\d*\.?\d+)', score_text)
            if match:
                score = float(match.group(1))
                return min(max(score, 0.0), 1.0)
                
        except Exception as e:
            logger.error(f"Memory AI importance analysis failed: {e}")
        
        # Fallback heuristic
        combined = f"{user_msg} {ai_msg}".lower()
        if any(word in combined for word in ['favorite', 'prefer', 'remember', 'important']):
            return 0.7
        elif any(word in combined for word in ['project', 'work', 'coding']):
            return 0.5
        elif any(word in combined for word in ['hello', 'hi', 'thanks']):
            return 0.2
        return 0.4
    
    def _generate_summary_with_memory_ai(self, user_msg: str, ai_msg: str, importance: float) -> str:
        """Generate conversation summary using memory AI"""
        prompt = f"""Summarize this conversation exchange in 1-2 sentences:

User: {user_msg}
AI: {ai_msg}

Summary:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Memory AI summary generation failed: {e}")
            return ""
    
    def _extract_facts_with_memory_ai(self, user_msg: str, ai_msg: str) -> Dict:
        """Extract profile facts using shared structured extractor."""
        try:
            from companion_ai.memory_ai import extract_smart_profile_facts
            return extract_smart_profile_facts(user_msg, ai_msg)
        except Exception as e:
            logger.error(f"Memory AI fact extraction failed: {e}")
            return {}
    
    def _generate_insight_with_memory_ai(self, user_msg: str, ai_msg: str, importance: float) -> str:
        """Generate user insights using memory AI"""
        if importance < core_config.IMPORTANCE_INSIGHT_MIN:
            return ""
            
        prompt = f"""Generate a brief insight about the user based on this conversation:

User: {user_msg}
AI: {ai_msg}

Insight:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Memory AI insight generation failed: {e}")
            return ""
    
    def _categorize_insight_with_memory_ai(self, insight: str) -> str:
        """Categorize insight using memory AI"""
        prompt = f"""Categorize this insight into ONE category:
- personality
- interests  
- preferences
- skills
- general

Insight: {insight}

Category:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=20
            )
            category = response.choices[0].message.content.strip().lower()
            if category in ['personality', 'interests', 'preferences', 'skills']:
                return category
        except Exception as e:
            logger.error(f"Memory AI categorization failed: {e}")
        
        return 'general'