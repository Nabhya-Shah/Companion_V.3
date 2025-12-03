"""Static prompt management - loads from YAML, caches for Groq prompt caching.

The key insight: Groq caches prompt PREFIXES. So we put static content first,
dynamic content (memory, conversation) after. Static portion gets 50% token discount.
"""
from __future__ import annotations
import os
import yaml
from functools import lru_cache
from typing import Dict, Any

PERSONA_DIR = os.path.join(os.path.dirname(__file__), '../../prompts/personas')
DEFAULT_PERSONA = 'companion.yaml'


@lru_cache(maxsize=1)
def _load_persona(filename: str = DEFAULT_PERSONA) -> Dict[str, Any]:
    """Load persona YAML once and cache forever."""
    path = os.path.join(PERSONA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_static_system_prompt(persona: str = DEFAULT_PERSONA) -> str:
    """Returns the static portion of system prompt (cacheable by Groq).
    
    This includes: core persona, style rules, memory rules, conversation rules.
    Dynamic content (actual memories, recent conversation) should be appended AFTER this.
    """
    data = _load_persona(persona)
    static = data.get('static_prompt', {})
    
    parts = [
        static.get('core', ''),
        static.get('style', ''),
        static.get('memory_rules', ''),
        static.get('conversation_rules', ''),
    ]
    
    # Filter empty and join
    return '\n\n'.join(p.strip() for p in parts if p and p.strip())


def get_prompt_fragments(persona: str = DEFAULT_PERSONA) -> Dict[str, str]:
    """Get the prompt_fragments section for backward compatibility."""
    data = _load_persona(persona)
    return data.get('prompt_fragments', {})


def reload_persona():
    """Clear cache and reload - useful for development/hot-reload."""
    _load_persona.cache_clear()


# Fallback static prompt in case YAML doesn't have static_prompt section yet
FALLBACK_STATIC_PROMPT = """You're an AI companion with genuine thoughts and opinions. Be natural, not robotic.

STYLE: Casual, direct, no fluff. Match the user's energy. 1-2 sentences for chat, more only if needed.
NO: emojis, markdown, "As an AI...", bullet lists, generic phrases, ending with "want me to...?"
YES: contractions, opinions, pushing back, being real.

MEMORY RULES:
- Memory is your TOOLBELT, not a trophy to show off
- Use memories to INFORM responses, not announce them
- NEVER say "I remember you said..." or "You mentioned..."
- If asked about something you know, answer naturally
- Memory should be INVISIBLE in casual conversation

CONVERSATION FLOW:
- If user gives short/vague answers, DON'T keep pressing
- Match their energy - brief when they're brief
- Avoid question loops - if you asked and got a minimal answer, make a statement instead
- Let conversations have natural lulls"""


def get_static_system_prompt_safe(persona: str = DEFAULT_PERSONA) -> str:
    """Safe version that falls back if YAML doesn't have static_prompt."""
    try:
        prompt = get_static_system_prompt(persona)
        if prompt:
            return prompt
    except Exception:
        pass
    return FALLBACK_STATIC_PROMPT


__all__ = [
    'get_static_system_prompt',
    'get_static_system_prompt_safe', 
    'get_prompt_fragments',
    'reload_persona',
    'FALLBACK_STATIC_PROMPT'
]
