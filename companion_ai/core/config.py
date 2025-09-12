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
ENABLE_TOOL_CALLING = False   # Legacy placeholder
ENABLE_STREAMING = False      # Planned Phase 3 (token streaming UX)
ENABLE_FTS = True             # Placeholder for future full-text search
ENABLE_PROMPT_CACHING = True  # Use provider prompt caching
ENABLE_STRUCTURED_FACTS = True
ENABLE_CAPABILITY_ROUTER = True
ENABLE_AUTO_TOOLS = True
VERIFY_FACTS_SECOND_PASS = True
ALWAYS_HEAVY_CHAT = False
AGGRESSIVE_ESCALATION = True
HEAVY_MEMORY = True
ENABLE_FACT_APPROVAL = os.getenv("ENABLE_FACT_APPROVAL", "true").lower() in ("1","true","yes")
FACT_AUTO_APPROVE = os.getenv("FACT_AUTO_APPROVE", "true").lower() in ("1","true","yes")
FACT_AUTO_APPROVE_MIN_CONF = float(os.getenv("FACT_AUTO_APPROVE_MIN_CONF", "0.8"))

# New flags
ENABLE_ENSEMBLE = os.getenv("ENABLE_ENSEMBLE", "false").lower() in ("1","true","yes")  # Multi-model ensemble reasoning
# Strategy options: choose | combine | choose_refine | combine_refine | refine_only
ENSEMBLE_MODE = os.getenv("ENSEMBLE_MODE", "choose_refine")
ENSEMBLE_CANDIDATES = int(os.getenv("ENSEMBLE_CANDIDATES", "3"))  # number of candidate model outputs (2 or 3 currently supported)
ENSEMBLE_REFINE_EXPANSION = float(os.getenv("ENSEMBLE_REFINE_EXPANSION", "0.25"))  # +25% token allowance for refinement
ENSEMBLE_REFINE_HARD_CAP = int(os.getenv("ENSEMBLE_REFINE_HARD_CAP", "300"))  # absolute cap tokens for refine stage
ENSEMBLE_MAX_TOTAL_FACTOR = float(os.getenv("ENSEMBLE_MAX_TOTAL_FACTOR", "2.5"))  # total token budget factor (candidates+judge+refine)
ENABLE_COMPOUND_MODELS = os.getenv("ENABLE_COMPOUND_MODELS", "false").lower() in ("1","true","yes")  # groq/compound models
ENABLE_EXPERIMENTAL_MODELS = os.getenv("ENABLE_EXPERIMENTAL_MODELS", "false").lower() in ("1","true","yes")  # qwen/moonshot

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
    # Fully-qualified GPT-OSS IDs (Groq naming uses openai/ prefix)
    "openai/gpt-oss-20b": {
        "speed": 2,
        "quality": 4,
        "cost_weight": 2,
        "tier": "smart_primary",
        "supports_reasoning_effort": True,
        "supports_reasoning_field": True,
        "default_temperature": 0.8,
        "roles": ["chat.primary","summary.standard","insight","facts"]
    },
    "openai/gpt-oss-120b": {
        "speed": 3,  # empirically still fast on Groq infra
        "quality": 5,
        "cost_weight": 5,
        "tier": "heavy_reasoning",
        "supports_reasoning_effort": True,
        "supports_reasoning_field": True,
        "default_temperature": 0.75,
        "roles": ["chat.heavy","reasoning","insight.high"]
    },
    # Experimental (enable via ENABLE_EXPERIMENTAL_MODELS)
    "qwen/qwen3-32b": {
        "speed": 3,
        "quality": 4,
        "cost_weight": 2,
        "tier": "experimental_balanced",
        "experimental": True,
        "roles": ["chat.primary","summary.standard"],
        "default_temperature": 0.75,
        "supports_reasoning_effort": False,
        "supports_reasoning_field": False
    },
    "moonshotai/kimi-k2-0905": {
        "speed": 4,
        "quality": 4,
        "cost_weight": 3,
        "tier": "experimental_long_context",
        "experimental": True,
        "roles": ["summary.high","reasoning"],
        "default_temperature": 0.7,
        "supports_reasoning_effort": False,
        "supports_reasoning_field": False
    },
    # Compound (agentic) models (enable via ENABLE_COMPOUND_MODELS)
    "groq/compound": {
        "speed": 3,
        "quality": 5,
        "cost_weight": 5,
        "tier": "agentic_full",
        "agentic": True,
        "roles": ["agent.compound"]
    },
    "groq/compound-mini": {
        "speed": 2,
        "quality": 4,
        "cost_weight": 3,
        "tier": "agentic_light",
        "agentic": True,
        "roles": ["agent.compound"]
    },
}

# Models that are confirmed available (defensive runtime fallback). Adjust as provider evolves.
KNOWN_AVAILABLE_MODELS = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "deepseek-r1-distill-llama-70b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "moonshotai/kimi-k2-0905",  # include kimi in available set for ensemble
}

def safest_fallback() -> str:
    """Return a model that is almost certainly present."""
    if DEFAULT_CONVERSATION_MODEL in KNOWN_AVAILABLE_MODELS:
        return DEFAULT_CONVERSATION_MODEL
    # pick any known
    return next(iter(KNOWN_AVAILABLE_MODELS))

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
SMART_PRIMARY_MODEL = "openai/gpt-oss-120b"  # user preference: smartest default generalist
HEAVY_MODEL = "deepseek-r1-distill-llama-70b"  # distinct heavy reasoner baseline
HEAVY_ALTERNATES = [
    "moonshotai/kimi-k2-0905",  # long-context / alternative reasoning perspective
    "openai/gpt-oss-120b"       # allow smart model to act as heavy fallback if needed
]
FAST_MODEL = DEFAULT_CONVERSATION_MODEL  # usually llama-3.1-8b-instant

def _resolve(model_name: str, fallback: str) -> str:
    return model_name if model_name in MODEL_CAPABILITIES else fallback

def choose_model(purpose: str, importance: float = 0.0, complexity: int = 0, return_reason: bool = False):  # override earlier definition
    """Aggressive smart routing with defensive fallback.

    If return_reason True returns (model, reason_dict).
    """
    reasons = {
        'purpose': purpose,
        'importance': importance,
        'complexity': complexity,
        'escalated': False,
        'fallback_used': False,
    }

    if ALWAYS_HEAVY_CHAT and purpose == 'chat':
        model = _resolve(HEAVY_MODEL, MODEL_ROLES.get('chat.primary', DEFAULT_CONVERSATION_MODEL))
        reasons['escalated'] = True
    else:
        primary = _resolve(SMART_PRIMARY_MODEL, MODEL_ROLES.get('chat.primary', DEFAULT_CONVERSATION_MODEL))
        heavy = _resolve(HEAVY_MODEL, MODEL_ROLES.get('reasoning', primary))
        fast = FAST_MODEL

        if purpose == 'facts':
            model = fast if fast in MODEL_CAPABILITIES else primary
        elif purpose == 'summary':
            if HEAVY_MEMORY and (importance >= 0.7 or (AGGRESSIVE_ESCALATION and importance >= 0.6 and complexity >=1)):
                legacy_high = MODEL_ROLES.get('memory.summary_high')
                if legacy_high and legacy_high != heavy:
                    model = legacy_high
                else:
                    model = heavy
                reasons['escalated'] = True
            else:
                model = primary if importance >= 0.4 else fast
        elif purpose == 'insight':
            if HEAVY_MEMORY and (importance >= 0.55 or complexity >= 2):
                legacy_high = MODEL_ROLES.get('memory.summary_high')
                if legacy_high and legacy_high != heavy:
                    model = legacy_high
                else:
                    model = heavy
                reasons['escalated'] = True
            else:
                model = fast if importance < 0.4 else primary
        elif purpose == 'reasoning':
            model = heavy
        elif purpose == 'chat':
            if complexity >= 2:
                legacy_reasoning = MODEL_ROLES.get('reasoning')
                if legacy_reasoning and legacy_reasoning != heavy:
                    model = legacy_reasoning
                else:
                    model = heavy
                reasons['escalated'] = True
            elif AGGRESSIVE_ESCALATION and complexity >=1:
                model = primary if primary != heavy else heavy
            else:
                model = primary
        else:
            model = primary

    # Defensive fallback if model unsupported by provider (e.g., 404 we saw during warmup)
    if model not in KNOWN_AVAILABLE_MODELS:
        reasons['fallback_used'] = True
        model = safest_fallback()

    if return_reason:
        return model, reasons
    return model

# ---- Simple Helpers ----
def require_auth(token: str | None) -> bool:
    """Return True if provided token matches configured API_AUTH_TOKEN (or auth disabled)."""
    if not API_AUTH_TOKEN:
        return True  # Auth not configured -> open (user private deployment)
    return token == API_AUTH_TOKEN
