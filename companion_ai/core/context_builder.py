"""Context Builder for adaptive single-persona prompt construction.

V4 Architecture:
 - Static prompt loaded from YAML and cached (for Groq prompt caching)
 - Dynamic context (memory, conversation) appended after static
 - Clean separation: prompts.py handles static, this handles dynamic
 - Mem0 integration: hybrid memory awareness when USE_MEM0=True
"""
from __future__ import annotations
import os, yaml, re
from typing import Dict, Any, List
import string
from . import config
from .prompts import get_static_system_prompt_safe
from companion_ai import memory as db
from .conversation_logger import log_interaction  # may be used externally

_persona_cache: Dict[str, Dict[str, Any]] = {}
STOPWORDS = { 'the','and','for','with','this','that','your','about','have','just','into','from','what','when','where','will','would','could','there','here','they','them','their','been','were','while','shall','should','those','these','over','under','onto','than','then','some','more','most','very','also','you','are','was','can','how','why','who','its','i','me','my','we','our' }

def load_persona(name: str | None = None) -> Dict[str, Any]:
    fname = name or 'companion.yaml'
    if fname in _persona_cache:
        return _persona_cache[fname]
    path = os.path.join(config.PERSONA_DIR, fname)
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    _persona_cache[fname] = data
    return data

def classify_mode(user_message: str) -> str:
    """Very simple heuristic classification for initial phase."""
    msg = user_message.lower().strip()
    if any(q in msg for q in ['how do', 'explain', 'what is', 'summarize', 'steps', 'define', 'difference between']):
        return 'informational'
    if len(msg.split()) <= 3 and any(w in msg for w in ['hi', 'hey', 'hello']):
        return 'conversational'
    if any(w in msg for w in ['feel', 'tired', 'sad', 'excited', 'happy', 'bored']):
        return 'conversational'
    return 'informational' if msg.endswith('?') else 'conversational'

def build_system_prompt(user_message: str, recent_conversation: str = "") -> str:
    """Build full system prompt: static (cached) + dynamic (memory, conversation)."""
    
    # ==========================================================================
    # STATIC PORTION - Cached by Groq (50% token discount)
    # ==========================================================================
    static_prompt = get_static_system_prompt_safe()
    
    # ==========================================================================
    # DYNAMIC PORTION - Changes per request, appended after static
    # ==========================================================================
    dynamic_parts = []
    
    # Memory context - use Mem0 or legacy based on config
    if config.USE_MEM0:
        memory_context = _build_mem0_context(user_message)
    else:
        memory_context = _build_memory_context(user_message)
    
    if memory_context:
        dynamic_parts.append(memory_context)
    
    # Recent conversation (limited to prevent token bloat)
    if recent_conversation:
        lines = recent_conversation.strip().split('\n')
        limited_history = '\n'.join(lines[-6:]) if len(lines) > 6 else recent_conversation
        dynamic_parts.append(f"Recent conversation:\n{limited_history}")
    
    # Combine: static first (for caching), then dynamic
    if dynamic_parts:
        return static_prompt + "\n\n" + "\n\n".join(dynamic_parts)
    return static_prompt


def _build_mem0_context(user_message: str) -> str:
    """Build memory context using Mem0 hybrid memory system.
    
    Returns formatted memory context with:
    - Stats (total memories, categories)
    - Auto-retrieved relevant memories
    - Hint about memory_search tool
    """
    try:
        from companion_ai.memory_v2 import build_memory_context, format_memory_for_prompt
        import logging
        logger = logging.getLogger(__name__)
        
        context = build_memory_context(
            user_message,
            user_id=config.MEM0_USER_ID,
            max_relevant=10  # Increased from config default to ensure better coverage
        )
        
        formatted = format_memory_for_prompt(context)
        logger.info(f"📚 Mem0 context: {context.stats.total_memories} memories, relevant: {len(context.relevant_memories)}")
        return formatted
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Mem0 context failed, falling back: {e}")
        return _build_memory_context(user_message)


def _build_memory_context(user_message: str) -> str:
    """Build memory context string if relevant to the message."""
    profile = db.get_all_profile_facts()
    if not profile:
        return ""
    
    user_lower = user_message.lower()
    
    # Explicit memory triggers (user is asking about past info)
    explicit_triggers = [
        'do you remember', 'what do you know', 'tell me about my',
        'remember when', 'like i said', 'i told you', 'we talked about',
        'last time', 'you know i', 'you know my', 'as i mentioned'
    ]
    
    # Implicit triggers (memory could help with personalization)
    implicit_triggers = [
        'recommend', 'suggest', 'what should', 'help me pick',
        'my favorite', 'i like', 'i prefer', 'i love', 'i hate',
        'for me', 'personalize', 'based on'
    ]
    
    explicit_memory = any(trigger in user_lower for trigger in explicit_triggers)
    implicit_memory = any(trigger in user_lower for trigger in implicit_triggers)
    
    if explicit_memory or implicit_memory:
        items = list(profile.items())[:5]
        if items:
            mem_str = ' | '.join(f"{k}: {v}" for k, v in items)
            return f"[What you know about this user: {mem_str}]"
    
    return ""

def build_system_prompt_with_meta(user_message: str, recent_conversation: str = "") -> dict:
    kw = extract_keywords(user_message, limit=3)
    profile = db.get_all_profile_facts()
    summaries = db.get_relevant_summaries(kw, 3) or db.get_latest_summary(2)
    insights = db.get_relevant_insights(kw, 3) or db.get_latest_insights(2)
    
    # Build system prompt with recent conversation context
    system_prompt = build_system_prompt(user_message, recent_conversation)
    
    memory_meta = {
        'profile_keys': list(profile.keys())[:5],
        'summary_ids': [s.get('id') for s in summaries],
        'insight_ids': [i.get('id') for i in insights],
        'keywords': kw
    }
    mode = classify_mode(user_message)
    return {'system_prompt': system_prompt, 'mode': mode, 'memory_meta': memory_meta}

__all__ = ["build_system_prompt", "build_system_prompt_with_meta", "classify_mode", "load_persona", "extract_keywords"]

def extract_keywords(text: str, limit: int = 5) -> List[str]:
    words: Dict[str,int] = {}
    for tok in text.lower().split():
        tok = tok.strip(string.punctuation)
        if not tok or tok in STOPWORDS or len(tok) < 3:
            continue
        words[tok] = words.get(tok,0)+1
    # deprioritize very common conversational verbs manually
    penalty = {'like','know','think','just','really'}
    scored = []
    tech = {'python','javascript','rust','go','java','tools','code','model','memory','ai'}
    for w,f in words.items():
        plural_bonus = 0.3 if w.endswith('s') and len(w) > 3 else 0
        tech_bonus = 0.6 if w in tech else 0
        adj = f + plural_bonus + tech_bonus - (0.5 if w in penalty else 0)
        scored.append((w, adj))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [w for w,_ in scored[:limit]]
