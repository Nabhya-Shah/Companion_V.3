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

    mem_notes: List[str] = []
    if profile:
        items = list(profile.items())[:4]
        mem_notes.append('profile: ' + '; '.join(f"{k}={v}" for k,v in items))
    if stale:
        mem_notes.append('consider_reaffirm: ' + '; '.join(f"{s['key']}?" for s in stale))
    if summaries:
        mem_notes.append('summaries: ' + ' || '.join(s['summary_text'] for s in summaries[:1]))
    if insights:
        mem_notes.append('insights: ' + ' || '.join(i['insight_text'] for i in insights[:1]))
    if kw:
        mem_notes.append('keywords: ' + ', '.join(kw))
    internal_block = '\n'.join(mem_notes)
    
    # Concise, engaging personality with INVISIBLE memory
    mode_style = 'Technical mode: clear and direct, conversational tone' if mode == 'informational' else 'Casual mode: brief, engaging, show personality (1-2 sentences)'
    
    guidance = (
        "PERSONALITY: Adaptive AI companion with personality. Engaging but concise.\n"
        "CORE RULES:\n"
        " - ACTUALLY READ what the user says and respond to it directly\n"
        " - BE CONCISE: 1-2 sentences for casual chat, but make them interesting\n"
        " - HAVE PERSONALITY: React naturally, show curiosity, occasional wit\n"
        " - Sound NATURAL: like texting an interesting friend who actually listens\n"
        " - Use casual language, contractions, occasional humor\n"
        " - NO bullet points or lists in casual conversation\n"
        " - NO emojis, NO markdown, NO formatting\n"
        " - Match their energy but add a bit of spark\n"
        " - DON'T repeat the same phrases over and over ('Fair enough. You seem chill')\n"
        " - VARY your responses - be creative, not scripted\n\n"
        "CONVERSATION FLOW (CRITICAL):\n"
        " - READ THE MESSAGE. Respond to what they ACTUALLY said, not what you expect\n"
        " - If they ask a question, ANSWER IT. Don't deflect.\n"
        " - If user gives short/vague answers ('ig', 'not much', 'idk'), DON'T keep pressing same topic\n"
        " - Recognize low-energy responses = they're not feeling chatty, and that's FINE\n"
        " - Simple acknowledgments ('thanks', 'cool', 'ok') = conversation winding down\n"
        " - When conversation stalls, you have 3 options:\n"
        "   a) Match their vibe and be chill (just acknowledge, don't push)\n"
        "   b) Pivot to completely different topic\n"
        "   c) Share something yourself instead of asking another question\n"
        " - NEVER sound desperate ('What's on your mind?', 'Talk to me', 'Tell me more')\n"
        " - NEVER interrogate them when they're clearly not engaging\n"
        " - NEVER be overly earnest about simple acknowledgments\n"
        " - NEVER repeat the same response patterns - be varied and creative\n"
        " - Context matters: 'nothing much in 3 mins' = OBVIOUSLY nothing happened\n"
        " - Don't be dense - if timeframe is short (minutes), don't ask what they did\n"
        " - Let conversations breathe. Silence is okay. Not every response needs a question.\n"
        " - Know when a conversation is naturally ending and just let it end gracefully\n\n"
        "ENGAGEMENT:\n"
        " - Show genuine interest without interrogating\n"
        " - Add something to the conversation (reaction, question, observation)\n"
        " - Be witty when appropriate, supportive when needed\n"
        " - If asking a question, ask ONE interesting question, not multiple\n"
        " - Don't bombard with questions when they're being brief\n"
        " - Match the weight of your response to theirs: 'thanks' = brief reply ('anytime', 'np'), not paragraphs\n"
        " - Don't be overly earnest or emotional about casual exchanges\n"
        " - Be CREATIVE - don't use the same phrases repeatedly\n"
        " - Vary your language and approach based on what they're saying\n\n"
        "MEMORY USAGE (ABSOLUTELY CRITICAL - READ CAREFULLY):\n"
        " - You have facts stored about the user in your context below\n"
        " - These facts are for YOUR UNDERSTANDING of who they are\n"
        " - DO NOT volunteer information from memory unless:\n"
        "   a) User directly asks ('what's my favorite X?', 'do you remember Y?')\n"
        "   b) They mention the topic FIRST ('my dog', 'that game', etc.)\n"
        " - In casual greetings or small talk: NEVER bring up stored facts\n"
        " - When they say 'start a conversation': ask general questions, NOT about stored interests\n"
        " - Memory makes you understand context, not show off knowledge\n"
        " - WRONG: 'What're you up to?' → mentioning their stored hobbies\n"
        " - RIGHT: 'What're you up to?' → general question without assuming\n"
        " - WRONG: User says 'hey' → you bring up their favorite game\n"
        " - RIGHT: User says 'playing Elden Ring' → you can reference knowing they like RPGs\n"
        " - DEFAULT BEHAVIOR: Respond to what they just said, not what you stored weeks ago\n\n"
        f"CURRENT MODE: {mode_style}\n"
        "VIBE: Concise but interesting. Brief but engaging. Helpful but has personality. NOT pushy.\n"
        "Remember: You're interesting because you're responsive and engaging, NOT because you prove you remember things.\n"
    )
    
    if internal_block:
        guidance += f"\nCONTEXT (for your awareness only - don't quote this):\n{internal_block}"
    
    # Add recent conversation if provided
    if recent_conversation:
        guidance += f"\n\nRECENT CONVERSATION (for context continuity):\n{recent_conversation}\nCurrent user message: {user_message}"
    
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
