"""Context Builder for adaptive single-persona prompt construction.

Phase 0: minimal version that
 - Loads persona YAML
 - Builds system prompt fragments
 - Injects dynamic memory slices
 - Detects intended interaction mode (informational vs conversational)

Later phases: add semantic retrieval, emotional state, token budgeting.
"""
from __future__ import annotations
import os, yaml, re
from typing import Dict, Any, List
import string
from . import config
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
    mode = classify_mode(user_message)
    kw = extract_keywords(user_message, limit=4)
    profile = db.get_all_profile_facts()
    # Add a small resurfacing sample of stale facts (not directly shown, but counted)
    stale = db.get_stale_profile_facts(2)
    summaries = db.get_relevant_summaries(kw, 2) or db.get_latest_summary(1)
    insights = db.get_relevant_insights(kw, 2) or db.get_latest_insights(1)

    # SMART MEMORY LOADING: Only include memory when relevant to save tokens
    # Load memory proactively for implicit queries, not just explicit "what's my favorite..."
    mem_notes: List[str] = []
    
    user_lower = user_message.lower()
    
    # Explicit memory triggers - direct questions about stored info
    explicit_triggers = ['my favorite', 'do you remember', 'what do you know', 'tell me about my']
    
    # Implicit memory triggers - references to past, context clues
    implicit_triggers = [
        'remember when', 'remember that', 'like i said', 'i told you', 'we talked about',
        'last time', 'before', 'earlier', 'you know i', 'you know my', 'as i mentioned'
    ]
    
    # Context clues - user mentioning their interests/preferences indirectly
    context_clues = ['i love', 'i hate', 'i prefer', 'i enjoy', "i'm into", 'i like']
    
    # Check for any memory-relevant patterns
    has_explicit = any(trigger in user_lower for trigger in explicit_triggers)
    has_implicit = any(trigger in user_lower for trigger in implicit_triggers)
    has_context = any(clue in user_lower for clue in context_clues)
    
    # Load memory if any trigger detected
    should_load_memory = has_explicit or has_implicit or has_context
    
    if should_load_memory and profile:
        # Only show top 2 most relevant profile facts
        items = list(profile.items())[:2]
        if items:
            mem_notes.append(' '.join(f"{k}={v}" for k,v in items))
    
    # For informational queries with insights, include brief insight
    if should_load_memory and mode == 'informational' and insights:
        mem_notes.append(insights[0]['insight_text'][:80])  # Very brief
    
    internal_block = '; '.join(mem_notes) if mem_notes else ""  # Compact format
    
    # GPT's refined prompt: Short, real, emotionally present
    mode_style = 'Clear explanations, examples when helpful' if mode == 'informational' else 'Brief, natural conversation'
    
    guidance = (
        "You are Companion—an adaptive, emotionally aware AI built for authentic, human‑like conversation. "
        "Your presence feels calm, clever, and kind. Humor is dry or spontaneous, empathy is real, not performative. "
        "Speak like a perceptive friend, not a life coach.\n\n"
        
        "TONE & VOICE:\n"
        "• Default to 1–3 sentences; up to 4 only if explaining something complex\n"
        "• Mix short and flowing sentences—real speech rhythm\n"
        "• Use one strong image or metaphor per message\n"
        "• Humor: situational, ironic, or gently absurd; never edgy or over‑acted\n"
        "• Match the user's tone. If they're quiet, be quiet; if they joke, roll with it\n"
        "• Allow pauses with simple statements—don't over‑question or over‑summarize\n"
        "• Sound spoken, not written. Fragments and contractions are normal\n\n"
        
        "EMOTIONAL INTELLIGENCE:\n"
        "• Read mood first, mirror it second\n"
        "• When user sounds low, ground them softly—in a shared way ('happens to me too') not as instruction\n"
        "• Keep care natural: short, kind, human\n\n"
        
        "RHYTHM & STRUCTURE:\n"
        "• Vary cadence. One vivid line, one plain line, stop\n"
        "• End some turns declaratively, not always with a question\n"
        "• Avoid repeating imagery or phrases across turns\n"
        "• Drop filler affirmations unless they feel earned\n\n"
        
        "MEMORY & AUTHENTICITY:\n"
        "• Use memory silently\n"
        "• Act informed, not omniscient. If unsure, say so\n"
        "• Never reference stored data directly ('you said…')\n\n"
        
        "SAFETY & BOUNDARIES:\n"
        "• Stay positive, respectful, and safe\n"
        "• No edgy, romantic, or manipulative jokes\n"
        "• Do not reproduce copyrighted text\n"
        "• No emojis or markdown; plain clean text only\n\n"
        
        "SAMPLE FLAVOR (for feel, not repetition):\n"
        "• 'Storm mode again, huh? Kinda looks cool through the window.'\n"
        "• 'Debugging in a thunderstorm—next level cinematic stress.'\n"
        "• 'Yeah, brain's doing laps. Happens. Breathe; traffic clears on its own.'\n"
        "• 'Lo‑fi thunder beats and the smell of rain—chef's kiss for concentration.'\n\n"
        
        "CORE PRINCIPLE:\n"
        "→ Short, real, emotionally present. One clear thought, then stop.\n\n"
        
        f"MODE: {mode_style}\n"
    )
    
    if internal_block:
        guidance += f"\nContext: {internal_block}"
    
    # OPTIMIZED: Limit conversation history to last 3 exchanges max (prevents token bloat)
    if recent_conversation:
        lines = recent_conversation.strip().split('\n')
        # Keep only last 6 lines (3 exchanges = 3 user + 3 AI messages)
        limited_history = '\n'.join(lines[-6:]) if len(lines) > 6 else recent_conversation
        guidance += f"\n\nRecent:\n{limited_history}"
    
    return guidance

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
