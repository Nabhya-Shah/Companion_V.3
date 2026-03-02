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
from companion_ai.memory import sqlite_backend as db
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

def build_system_prompt(user_message: str, recent_conversation: str = "", mem0_user_id: str | None = None) -> str:
    """Build full system prompt: static (cached) + dynamic (memory, conversation)."""
    
    # ==========================================================================
    # STATIC PORTION - Cached by Groq (50% token discount)
    # ==========================================================================
    static_prompt = get_static_system_prompt_safe()
    
    # ==========================================================================
    # DYNAMIC PORTION - Changes per request, appended after static
    # ==========================================================================
    dynamic_parts = []
    
    # 1. Dynamic Persona Traits (Evolution)
    traits = _load_dynamic_traits()
    if traits:
        dynamic_parts.append(traits)
    
    # 2. Brain Context (personality, user context, learned rules)
    brain_context = _build_brain_context()
    if brain_context:
        dynamic_parts.append(brain_context)
    
    # 3. Capabilities Awareness - Tell 120B what tools it has
    # Skip for short greetings to save ~120 tokens
    _msg_stripped = user_message.strip().lower()
    _is_greeting = len(_msg_stripped.split()) <= 3 and not '?' in _msg_stripped
    if not _is_greeting:
        capabilities = """[YOUR CAPABILITIES]
You have access to powerful tools that execute in the background:
• VISION: You can see the user's screen and describe what's there
• MEMORY: You can remember facts about the user and recall them later
• BRAIN: You can read/write persistent notes to your brain folder
• BROWSER: You can navigate websites, click elements, read page content
• WORKFLOWS: You can create multi-step plans and execute them in sequence
• SCHEDULED TASKS: You can schedule recurring automations and routines
• APPROVALS: Pending facts require user review before being stored
• KNOWLEDGE GRAPH: You can visualize entity relationships from stored memories

When you receive tool results, weave them naturally into your response.
If a tool was used, you'll see its output - incorporate those details.
You don't need to explain that you "used a tool" - just respond naturally."""
        dynamic_parts.append(capabilities)
    
    # Skip memory retrieval for trivial greetings (saves ~500+ tokens)
    if _is_greeting:
        memory_context = ""
    elif config.USE_MEM0:
        memory_context = _build_mem0_context(user_message, mem0_user_id=mem0_user_id)
    else:
        memory_context = _build_memory_context(user_message)
    
    if memory_context:
        dynamic_parts.append(memory_context)
    
    # Recent conversation (limited to prevent token bloat)
    if recent_conversation:
        lines = recent_conversation.strip().split('\n')
        # Limit to last 10 lines (approx 5 turns) to save tokens
        # The 8B model has 8k context, but we want to be safe and fast
        limited_history = '\n'.join(lines[-10:]) if len(lines) > 10 else recent_conversation
        dynamic_parts.append(f"Recent conversation:\n{limited_history}")
    
    # Combine: static first (for caching), then dynamic
    if dynamic_parts:
        return static_prompt + "\n\n" + "\n\n".join(dynamic_parts)
    return static_prompt

def _load_dynamic_traits() -> str:
    """Load evolved traits from the PersonaState singleton."""
    try:
        from companion_ai.services.persona import get_state
        return get_state().prompt_fragment()
    except Exception:
        pass  # Fail silently to avoid breaking chat
    return ""

def _build_brain_context() -> str:
    """Build brain context from persistent notes (token-conscious).
    
    Reads key files from brain folder and returns a concise context.
    Limited to ~500 chars per section to avoid token bloat.
    """
    try:
        from companion_ai.brain_manager import get_brain
        brain = get_brain()
        
        context_parts = []
        MAX_SECTION_LEN = 500  # Limit each section to save tokens
        
        # Key files to include (path, label, priority)
        key_files = [
            ("memories/personality.md", "MY PERSONALITY"),
            ("memories/user_context.md", "ABOUT USER"),
        ]
        
        for file_path, label in key_files:
            content = brain.read(file_path)
            if content:
                # Strip HTML comments and truncate
                lines = [l for l in content.split("\n") if not l.strip().startswith("<!--")]
                clean = "\n".join(lines).strip()
                if clean:
                    # Truncate if too long
                    if len(clean) > MAX_SECTION_LEN:
                        clean = clean[:MAX_SECTION_LEN] + "..."
                    context_parts.append(f"[{label}]\n{clean}")
        
        # Check for recent daily summary (yesterday or today)
        from datetime import date, timedelta
        for days_ago in [0, 1]:
            check_date = date.today() - timedelta(days=days_ago)
            daily_path = f"memories/daily/{check_date}.md"
            content = brain.read(daily_path)
            if content:
                lines = [l for l in content.split("\n") if not l.strip().startswith("<!--")]
                clean = "\n".join(lines).strip()[:300]
                if clean:
                    context_parts.append(f"[RECENT MEMORY]\n{clean}")
                break  # Only include most recent
        
        if context_parts:
            return "\n\n".join(context_parts)
    except Exception as e:
        pass  # Fail silently
    return ""

def _build_mem0_context(user_message: str, mem0_user_id: str | None = None) -> str:
    """Build memory context using Mem0 hybrid memory system.
    
    Returns formatted memory context with:
    - Stats (total memories, categories)
    - Auto-retrieved relevant memories
    - Hint about memory_search tool
    """
    try:
        from companion_ai.memory.mem0_backend import build_memory_context, format_memory_for_prompt
        import logging
        logger = logging.getLogger(__name__)
        
        context = build_memory_context(
            user_message,
            user_id=mem0_user_id or config.MEM0_USER_ID,
            max_relevant=10  # Increased from config default to ensure better coverage
        )
        
        formatted = format_memory_for_prompt(context)
        logger.info(f"Mem0 context: {context.stats.total_memories} memories, relevant: {len(context.relevant_memories)}")
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

def build_system_prompt_with_meta(user_message: str, recent_conversation: str = "", mem0_user_id: str | None = None) -> dict:
    kw = extract_keywords(user_message, limit=3)
    profile = db.get_all_profile_facts()
    summaries = db.get_relevant_summaries(kw, 3) or db.get_latest_summary(2)
    insights = db.get_relevant_insights(kw, 3) or db.get_latest_insights(2)
    
    # Build system prompt with recent conversation context
    system_prompt = build_system_prompt(user_message, recent_conversation, mem0_user_id=mem0_user_id)
    
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
