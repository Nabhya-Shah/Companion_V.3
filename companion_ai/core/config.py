"""Central configuration for Companion AI (Phase 0).

All tunable constants, model names, thresholds, and environment lookups live here
so other modules do not hard-code values. Later phases can extend this with
capability metadata, model latency profiling, etc.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ---- Environment / Secrets (never commit actual keys) ----
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MEMORY_API_KEY = os.getenv("GROQ_MEMORY_API_KEY") or GROQ_API_KEY
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")  # For web write endpoints

# ---- Models (central names) ----
# Conversation default model (balanced speed/quality)
DEFAULT_CONVERSATION_MODEL = "llama-3.1-8b-instant"
# Reasoning / larger context (optional future)
REASONING_MODEL = "deepseek-r1-distill-llama-70b"
# Memory / fast analytic model
MEMORY_FAST_MODEL = "llama-3.1-8b-instant"
# (Reserved) higher quality memory analysis model
MEMORY_DEEP_MODEL = "llama-3.3-70b-versatile"

# ---- Model Role Mapping (Phase 1) ----
# Central place to modify which model handles which purpose. Adjust freely.
MODEL_ROLES = {
    "chat.primary": "llama-3.3-70b-versatile",     # Highest quality default chat
    "chat.fast_fallback": DEFAULT_CONVERSATION_MODEL,
    "reasoning": REASONING_MODEL,
    "memory.summary_high": "llama-3.3-70b-versatile",
    "memory.summary_standard": MEMORY_FAST_MODEL,
    "memory.fact_extract": MEMORY_FAST_MODEL,
}

REASONING_KEYWORDS = {
    "analyze","analysis","explain","step-by-step","derive","proof","prove","algorithm",
    "optimize","design","plan","evaluate","compare","contrast","break down","architecture",
    "strategy","improve","build"
}

def classify_complexity(message: str) -> int:
    """Return rough complexity level 0..3 based on heuristics.
    0 = casual, 1 = normal, 2 = analytical, 3 = deep reasoning.
    """
    m = message.lower()
    word_count = len(m.split())
    kw_hits = sum(1 for k in REASONING_KEYWORDS if k in m)
    question_marks = m.count('?')
    if word_count > 160 or kw_hits >= 3:
        return 3
    if word_count > 100 or kw_hits >= 2 or question_marks >= 3:
        return 2
    if word_count > 40 or kw_hits == 1 or question_marks >= 2:
        return 1
    return 0

def choose_model(purpose: str, importance: float = 0.0, complexity: int = 0) -> str:
    """Select model based on purpose + metadata.
    purpose: 'chat' | 'summary' | 'facts' | 'insight' | 'reasoning'
    importance: 0..1 significance (memory gating)
    complexity: 0..3 from classify_complexity
    """
    # Reasoning escalation first
    if purpose == 'chat' and complexity >= 2:
        return MODEL_ROLES.get('reasoning', MODEL_ROLES['chat.primary'])
    if purpose == 'reasoning':
        return MODEL_ROLES.get('reasoning', MODEL_ROLES['chat.primary'])
    if purpose == 'summary':
        if importance >= 0.7:
            return MODEL_ROLES.get('memory.summary_high', MODEL_ROLES['chat.primary'])
        return MODEL_ROLES.get('memory.summary_standard', MODEL_ROLES['chat.fast_fallback'])
    if purpose in ('facts','fact_extract'):
        return MODEL_ROLES.get('memory.fact_extract', MODEL_ROLES['chat.fast_fallback'])
    if purpose == 'insight':
        # Promote insights when importance moderate
        if importance >= 0.6:
            return MODEL_ROLES.get('memory.summary_high', MODEL_ROLES['chat.primary'])
        return MODEL_ROLES.get('memory.summary_standard', MODEL_ROLES['chat.fast_fallback'])
    # default chat path
    return MODEL_ROLES.get('chat.primary', DEFAULT_CONVERSATION_MODEL)

# ---- Prompt / Persona Paths ----
PERSONA_DIR = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), '..', 'prompts', 'personas')
DEFAULT_PERSONA = "companion.yaml"

# ---- Memory Retrieval Limits / Thresholds ----
SUMMARY_LIMIT = 5
INSIGHT_LIMIT = 8
IMPORTANCE_MIN_STORE = 0.2
IMPORTANCE_INSIGHT_MIN = 0.4

# ---- SQLite / Data ----
DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), '..', 'data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')

# ---- Utility Dataclasses (future extensibility) ----
@dataclass
class ModelConfig:
    name: str
    max_output_tokens: int = 1024
    temperature: float = 0.8

CONVERSATION_MODEL_CONFIG = ModelConfig(name=DEFAULT_CONVERSATION_MODEL)
MEMORY_MODEL_CONFIG = ModelConfig(name=MEMORY_FAST_MODEL, temperature=0.3)

# ---- Feature Flags (Phase gating) ----
ENABLE_TOOL_CALLING = False  # Will turn on in later phases
ENABLE_STREAMING = False     # Planned Phase 3
ENABLE_FTS = True            # Phase 0 quick win placeholder
ENABLE_PROMPT_CACHING = True # Use Groq prompt caching when available
ENABLE_STRUCTURED_FACTS = True # Use structured outputs for fact extraction if SDK supports
ENABLE_CAPABILITY_ROUTER = True # Use capability metadata to inform selection (non-breaking initial)
ENABLE_AUTO_TOOLS = True       # Allow heuristic autonomous tool invocation
VERIFY_FACTS_SECOND_PASS = True # Second-pass heavy model verification of extracted facts
ALWAYS_HEAVY_CHAT = False       # Force all chat on heavy model (developer showcase)
AGGRESSIVE_ESCALATION = True    # Lower thresholds for heavy escalation
HEAVY_MEMORY = True             # Use heavy model for important memory ops (summary/insight)

# ---- Model Capability Registry ----
# Light metadata to support smarter routing and future observability. Values are heuristic.
# speed: 1(fast) .. 5(slowest) relative; quality: 1(low) .. 5(high). cost_weight rough relative.
MODEL_CAPABILITIES: dict[str, dict] = {
    "llama-3.1-8b-instant": {
        "speed": 1,
        "quality": 2,
        "cost_weight": 1,
        "tier": "fast",
        "supports_reasoning_effort": False,
        "supports_reasoning_field": False,
        "default_temperature": 0.8,
        "roles": ["chat.fast_fallback","facts","summary.standard"]
    },
    "llama-3.3-70b-versatile": {
        "speed": 3,
        "quality": 4,
        "cost_weight": 3,
        "tier": "balanced_high",
        "supports_reasoning_effort": False,
        "supports_reasoning_field": False,
        "default_temperature": 0.8,
        "roles": ["chat.primary","summary.high","insight"]
    },
    "deepseek-r1-distill-llama-70b": {
        "speed": 4,
        "quality": 5,
        "cost_weight": 4,
        "tier": "reasoning",
        "supports_reasoning_effort": False,  # placeholder until verified
        "supports_reasoning_field": False,
        "default_temperature": 0.7,
        "roles": ["reasoning","analysis"]
    },
    # Newly exposed Groq GPT-OSS models (names tentative — adjust if provider differs)
    "gpt-oss-20b": {
        "speed": 2,
        "quality": 4,
        "cost_weight": 2,
        "tier": "smart_primary",
        "supports_reasoning_effort": True,
        "supports_reasoning_field": True,
        "default_temperature": 0.8,
        "roles": ["chat.primary","summary.standard","insight","facts"]
    },
    "gpt-oss-120b": {
        "speed": 3,  # empirically still fast on Groq infra
        "quality": 5,
        "cost_weight": 5,
        "tier": "heavy_reasoning",
        "supports_reasoning_effort": True,
        "supports_reasoning_field": True,
        "default_temperature": 0.75,
        "roles": ["chat.heavy","reasoning","insight.high"]
    },
}

def model_capability_summary() -> dict:
    """Return safe subset of capability metadata for external /health display."""
    out = {}
    for name, meta in MODEL_CAPABILITIES.items():
        out[name] = {
            'tier': meta.get('tier'),
            'speed': meta.get('speed'),
            'quality': meta.get('quality'),
            'supports_reasoning_effort': meta.get('supports_reasoning_effort'),
        }
    return out

# ---- Adaptive Routing (aggressive-smart profile) ----
SMART_PRIMARY_MODEL = "gpt-oss-20b"
HEAVY_MODEL = "gpt-oss-120b"
FAST_MODEL = DEFAULT_CONVERSATION_MODEL  # usually llama-3.1-8b-instant

def _resolve(model_name: str, fallback: str) -> str:
    return model_name if model_name in MODEL_CAPABILITIES else fallback

def choose_model(purpose: str, importance: float = 0.0, complexity: int = 0) -> str:  # override earlier definition
    """Aggressive smart routing.
    purpose: 'chat' | 'summary' | 'facts' | 'insight' | 'reasoning'
    importance: 0..1 (memory importance)
    complexity: 0..3 heuristic
    """
    # Hard override
    if ALWAYS_HEAVY_CHAT and purpose == 'chat':
        return _resolve(HEAVY_MODEL, MODEL_ROLES.get('chat.primary', DEFAULT_CONVERSATION_MODEL))

    primary = _resolve(SMART_PRIMARY_MODEL, MODEL_ROLES.get('chat.primary', DEFAULT_CONVERSATION_MODEL))
    heavy = _resolve(HEAVY_MODEL, MODEL_ROLES.get('reasoning', primary))
    fast = FAST_MODEL

    if purpose == 'facts':
        # Keep extraction terse; use fast model first
        return fast if fast in MODEL_CAPABILITIES else primary

    if purpose == 'summary':
        if HEAVY_MEMORY and (importance >= 0.7 or (AGGRESSIVE_ESCALATION and importance >= 0.6 and complexity >=1)):
            legacy_high = MODEL_ROLES.get('memory.summary_high')
            if legacy_high and legacy_high != heavy:
                return legacy_high
            return heavy
        return primary if importance >= 0.4 else fast

    if purpose == 'insight':
        if HEAVY_MEMORY and (importance >= 0.55 or complexity >= 2):
            legacy_high = MODEL_ROLES.get('memory.summary_high')
            if legacy_high and legacy_high != heavy:
                return legacy_high
            return heavy
        # Low importance -> fast (legacy expectation), else primary
        return fast if importance < 0.4 else primary

    if purpose == 'reasoning':
        return heavy

    if purpose == 'chat':
        # Escalation triggers
        if complexity >= 2:
            legacy_reasoning = MODEL_ROLES.get('reasoning')
            if legacy_reasoning and legacy_reasoning != heavy:
                return legacy_reasoning
            return heavy
        if AGGRESSIVE_ESCALATION and complexity >=1:
            return primary if primary != heavy else heavy
        return primary

    # Fallback
    return primary

# ---- Simple Helpers ----
def require_auth(token: str | None) -> bool:
    """Return True if provided token matches configured API_AUTH_TOKEN (or auth disabled)."""
    if not API_AUTH_TOKEN:
        return True  # Auth not configured -> open (user private deployment)
    return token == API_AUTH_TOKEN
