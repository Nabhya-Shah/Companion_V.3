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

def build_system_prompt(user_message: str) -> str:
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
    mode_style = 'INFORMATIONAL: structured, accurate answer; add ONE clarifying question if ambiguity remains.' if mode == 'informational' else 'CONVERSATIONAL: concise, natural, subtle follow-up when helpful.'
    guidance = (
        "ROLE: Adaptive companion (Jarvis-like).\n"
        "RULES:\n"
        " - Plain text only (no markdown / emojis / asterisks).\n"
        " - Use memory implicitly; do not dump raw memory labels.\n"
        " - Ask for clarification when key parameters missing.\n"
        " - Avoid repeating generic lists; deepen or narrow focus.\n"
        " - Bullet answers: '-' prefix, <=6 items.\n"
        " - End with brief next-step or question unless user opts out.\n"
        " - Show planned tool usage as TOOL:name:query when helpful (search, calc, time).\n"
        " - Never store assumptions; only explicit user facts.\n"
        f"MODE: {mode_style}\n"
        "MEMORY: Integrate relevant traits subtly.\n"
        "SANITIZE: remove markdown if any sneaks in."
    )
    return guidance + (f"\nINTERNAL MEMORY (not to quote):\n{internal_block}" if internal_block else '')

def build_system_prompt_with_meta(user_message: str) -> dict:
    kw = extract_keywords(user_message, limit=3)
    profile = db.get_all_profile_facts()
    summaries = db.get_relevant_summaries(kw, 3) or db.get_latest_summary(2)
    insights = db.get_relevant_insights(kw, 3) or db.get_latest_insights(2)
    system_prompt = build_system_prompt(user_message)
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
