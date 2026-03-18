"""
Simplified Configuration for Companion AI v0.3

4-Model Architecture:
- PRIMARY (120B): Main chat, reasoning, everything 
- TOOLS (Scout): Native function calling
- VISION (Maverick): Image analysis (separate API key)
- COMPOUND: Web search, weather, calculations
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# API KEYS
# ============================================================================

# V6 Architecture toggle - Enable local loop orchestration
# When True, uses the 120B orchestrator to decide if local loops should handle tasks
USE_ORCHESTRATOR = os.getenv("USE_ORCHESTRATOR", "true").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_TOOL_API_KEY = os.getenv("GROQ_TOOL_API_KEY")  # Dedicated key for tool planner
GROQ_VISION_API_KEY = os.getenv("GROQ_VISION_API_KEY", GROQ_API_KEY)  # Falls back to main key

# Key Rotation Support
# Load all Groq keys into rotation pool (main + named + numbered)
GROQ_API_KEYS = [GROQ_API_KEY] if GROQ_API_KEY else []

# Add named keys (these have specific purposes but can be used for rotation)
for env_var in ["GROQ_VISION_API_KEY", "GROQ_MEMORY_API_KEY", "GROQ_TOOL_API_KEY", "GROQ_VOICE_API_KEY"]:
    key = os.getenv(env_var)
    if key and key not in GROQ_API_KEYS and key != GROQ_API_KEY:
        GROQ_API_KEYS.append(key)

# Add numbered keys (GROQ_API_KEY_2, GROQ_API_KEY_3, etc.)
for i in range(2, 10):
    key = os.getenv(f"GROQ_API_KEY_{i}")
    if key and key not in GROQ_API_KEYS:
        GROQ_API_KEYS.append(key)

# External service keys
SERPER_API_KEY = os.getenv("SERPER_API_KEY")  # For custom web search if needed

# Security
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")  # Protects write endpoints

# Workspace feature permissions (Sprint 4)
WORKSPACE_PERMISSIONS_PATH = os.getenv("WORKSPACE_PERMISSIONS_PATH", os.path.join("data", "workspace_permissions.json"))
DEFAULT_TOOLS_EXECUTE = os.getenv("DEFAULT_TOOLS_EXECUTE", "true").lower() == "true"
DEFAULT_MEMORY_WRITE = os.getenv("DEFAULT_MEMORY_WRITE", "true").lower() == "true"
DEFAULT_WORKFLOWS_RUN = os.getenv("DEFAULT_WORKFLOWS_RUN", "true").lower() == "true"
DEFAULT_FILES_UPLOAD = os.getenv("DEFAULT_FILES_UPLOAD", "true").lower() == "true"

FEATURE_PERMISSION_DEFAULTS = {
    "tools_execute": DEFAULT_TOOLS_EXECUTE,
    "memory_write": DEFAULT_MEMORY_WRITE,
    "workflows_run": DEFAULT_WORKFLOWS_RUN,
    "files_upload": DEFAULT_FILES_UPLOAD,
}

# Tool safety policy (Sprint B)
# When TOOL_ALLOWLIST is set, only listed tool names can execute.
# Use '*' to allow all tools.
TOOL_ALLOWLIST = os.getenv("TOOL_ALLOWLIST", "").strip()

# Phase 3 plugin policy
# When PLUGIN_ALLOWLIST is set, only listed plugins are enabled.
# Use '*' or empty to enable all plugins.
PLUGIN_ALLOWLIST = os.getenv("PLUGIN_ALLOWLIST", "").strip()
PLUGIN_POLICY_PATH = os.getenv("PLUGIN_POLICY_PATH", os.path.join("data", "plugin_policy.json"))
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "main").strip().lower()

def require_auth(token: str) -> bool:
    """Check if token is valid. Returns True if auth disabled or token matches."""
    if not API_AUTH_TOKEN:
        return True  # No auth configured = allow all
    return token == API_AUTH_TOKEN


def get_tool_allowlist() -> set[str] | None:
    """Return normalized tool allowlist, or None when policy is disabled.

    None means no allowlist policy is applied.
    """
    raw = (TOOL_ALLOWLIST or "").strip()
    if not raw:
        return None
    if raw == "*":
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def get_plugin_allowlist() -> set[str] | None:
    """Return normalized plugin allowlist, or None when policy is disabled."""
    raw = (PLUGIN_ALLOWLIST or "").strip()
    if not raw:
        return None
    if raw == "*":
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}

# ============================================================================
# MODEL CONFIGURATION - V4 Architecture
# ============================================================================
# V4 Philosophy: 120B decides, fast models execute
# - PRIMARY: Main personality, synthesis, decisions
# - TOOLS: Native function calling (Scout for now, 8B planned)
# - VISION: Image analysis only
# - COMPOUND: Web/weather fast path

PRIMARY_MODEL = "openai/gpt-oss-120b"  # Final synthesis, personality, smart responses
TOOLS_MODEL = "llama-3.1-8b-instant"  # Light tools via Groq (fast, free tier)
TOOLS_MODEL_FAST = "llama-3.1-8b-instant"  # Backup
VISION_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"  # Cloud vision (fallback)
MEMORY_PROCESSING_MODEL = os.getenv("MEMORY_PROCESSING_MODEL", "llama-3.3-70b-versatile")
MEMORY_FAST_MODEL = os.getenv("MEMORY_FAST_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# ============================================================================
# HYBRID MODEL ROUTING - The Core of V5 Architecture
# ============================================================================
# LIGHT TOOLS: Simple operations, low tokens → Groq cloud (fast, free)
# HEAVY TOOLS: Vision, files, computer, memory → Local Ollama (free, parallel)
# ============================================================================

# Local models for heavy operations (saves Groq tokens!)
# NOTE: Now using vLLM backend instead of Ollama - use HuggingFace format
LOCAL_HEAVY_MODEL = os.getenv("LOCAL_HEAVY_MODEL", "Qwen/Qwen2.5-3B-Instruct")  # vLLM model
LOCAL_VISION_MODEL = os.getenv("LOCAL_VISION_MODEL", "llava:13b")  # Vision analysis (still Ollama for now)
MEMORY_LOCAL_MODEL = os.getenv("MEMORY_LOCAL_MODEL", LOCAL_HEAVY_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
MEMORY_PROCESSING_PROVIDER = os.getenv("MEMORY_PROCESSING_PROVIDER", "groq").strip().lower()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").strip().lower()
MEMORY_EXTRACT_PREFER_FAST = os.getenv("MEMORY_EXTRACT_PREFER_FAST", "true").lower() == "true"

# Tool categorization - determines routing
LIGHT_TOOLS = {
    "wikipedia_lookup",     # Simple web lookup
    "get_current_time",     # Trivial
    "start_background_task", # Just scheduling
    "consult_compound",     # Web search
}

HEAVY_TOOLS = {
    "look_at_screen",       # Vision - big tokens
    "use_computer",         # Multi-step, needs vision
    "browser_goto",         # Web automation
    "browser_click",
    "browser_type",
    "browser_read",
    "browser_press",
    "brain_read",           # File operations
    "brain_write",
    "brain_list",
    "memory_search",        # Memory retrieval
    "read_pdf",             # Document parsing
    "read_image_text",      # OCR
}


def is_heavy_tool(tool_name: str) -> bool:
    """Check if a tool should use local heavy model."""
    return tool_name in HEAVY_TOOLS


def get_tool_model(tool_name: str = None) -> tuple[str, bool]:
    """Get the appropriate model for a tool.
    
    Returns:
        tuple: (model_name, is_local)
        - is_local=True means use Ollama client
        - is_local=False means use Groq client
    """
    if tool_name and tool_name in HEAVY_TOOLS:
        return LOCAL_HEAVY_MODEL, True
    return TOOLS_MODEL, False  # Light tools use Groq


# Model capabilities reference
MODEL_INFO = {
    "openai/gpt-oss-120b": {
        "description": "Primary model - handles all chat, reasoning, analysis",
        "context_window": 131072,
        "tool_use": False,  # Use Scout for tools
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "description": "Native function calling with tools",
        "context_window": 131072,
        "tool_use": True,
    },
    "meta-llama/llama-4-maverick-17b-128e-instruct": {
        "description": "Vision model for image analysis",
        "context_window": 131072,
        "vision": True,
    },
    "llama-3.1-8b-instant": {
        "description": "Fast tool executor - 560 tps, cheap",
        "context_window": 131072,
        "tool_use": True,
    },
    "llama-3.3-70b-versatile": {
        "description": "Primary memory-processing baseline for extraction and review quality",
        "context_window": 131072,
        "tool_use": False,
    },
}


def get_tool_executor() -> str:
    """Get the DEFAULT model for tool execution (light tools).
    
    NOTE: Heavy tools (vision, browser, files) are automatically routed to
    LOCAL_HEAVY_MODEL (qwen2.5:32b) inside generate_model_response_with_tools
    based on intent detection. This function returns the Groq model for light tools.
    """
    return TOOLS_MODEL  # Groq 8B for light tools (fast, reliable)


# ============================================================================
# SIMPLE MODEL SELECTION
# ============================================================================
def choose_model(task: str = 'chat', complexity: int = 1, importance: float = 0.5, return_reason: bool = False):
    """
    Simple model selection - returns PRIMARY_MODEL for almost everything.
    
    Args:
        task: Task type ('chat', 'tools', 'vision', 'summary', 'facts', 'insight')
        complexity: 0-2 (not used for escalation anymore)
        importance: 0-1 (not used for escalation anymore)
        return_reason: If True, return (model, routing_meta) tuple
    
    Returns:
        model name, or (model, routing_meta) if return_reason=True
    """
    task = (task or 'chat').strip().lower()

    # Simple task-based routing
    if task in ('tools', 'function_calling'):
        model = TOOLS_MODEL
    elif task in ('vision', 'image', 'screen'):
        model = VISION_MODEL
    elif task in ('memory_processing', 'memory', 'summary', 'facts', 'insight'):
        model = MEMORY_PROCESSING_MODEL
    # V5: compound/web_search now use PRIMARY_MODEL (120B has built-in search)
    else:
        # Everything else uses PRIMARY_MODEL (chat, reasoning, web_search)
        model = PRIMARY_MODEL
    
    if return_reason:
        routing_meta = {
            'task': task,
            'complexity': complexity,
            'model': model,
            'routing': 'simple_task_based'
        }
        return model, routing_meta
    
    return model


def get_model_for_task(task: str) -> str:
    """Get the appropriate model for a specific task type."""
    return choose_model(task=task)


def get_memory_processing_model(task: str = 'memory_processing', prefer_fast: bool = False) -> tuple[str, bool, str]:
    """Return the configured memory-processing model.

    Returns:
        tuple: (model_name, is_local, provider)
    """
    provider = MEMORY_PROCESSING_PROVIDER if MEMORY_PROCESSING_PROVIDER in {'groq', 'local', 'auto'} else 'groq'
    if provider == 'local':
        return MEMORY_LOCAL_MODEL, True, 'local'
    if prefer_fast and MEMORY_EXTRACT_PREFER_FAST:
        return MEMORY_FAST_MODEL, False, 'groq'
    return MEMORY_PROCESSING_MODEL, False, 'groq'


def get_embedding_model() -> tuple[str, str]:
    """Return the configured embedding model and provider."""
    provider = EMBEDDING_PROVIDER or 'ollama'
    return EMBEDDING_MODEL, provider


# ============================================================================
# MEMORY CONFIGURATION
# ============================================================================
MEMORY_SEARCH_LIMIT = 10
MEMORY_RELEVANCE_THRESHOLD = 0.5
MEMORY_GRAPH_ENABLED = True
MEMORY_AUTO_EXTRACT = True
IMPORTANCE_MIN_STORE = 0.3  # Minimum importance score to store in memory
IMPORTANCE_INSIGHT_MIN = 0.4  # Minimum importance to generate insights

# Confidence-based fact system (D2)
ENABLE_FACT_APPROVAL = os.getenv("ENABLE_FACT_APPROVAL", "true").lower() == "true"  # When True, low-confidence facts require review
FACT_CONFIDENCE_THRESHOLD = 0.5  # Facts below this are "pending review"
FACT_AUTO_APPROVE_THRESHOLD = 0.85  # Facts at/above this are auto-approved

# Graph search modes
GRAPH_SEARCH_MODES = [
    "GRAPH_COMPLETION",
    "KEYWORD", 
    "RELATIONSHIPS",
    "TEMPORAL",
    "IMPORTANT",
]

# ============================================================================
# MEM0 CONFIGURATION
# ============================================================================
# Feature flag: Use Mem0 for memory instead of SQLite + NetworkX
USE_MEM0 = True  # Enabled for V4 testing

# Mem0 settings
MEM0_USER_ID = "default"  # Default user ID for single-user mode
MEM0_MAX_RELEVANT = 10  # Max auto-retrieved memories per request (Increased for better recall)
MEM0_MODEL = MEMORY_FAST_MODEL  # Fast model for memory-side helper operations

# ============================================================================
# CONTEXT BUILDING
# ============================================================================
MAX_CONTEXT_TOKENS = 8000
MAX_MEMORY_CONTEXT_TOKENS = 2000
MAX_GRAPH_CONTEXT_TOKENS = 1500
RECENT_TURNS_IN_CONTEXT = 10

# ============================================================================
# CONVERSATION SETTINGS
# ============================================================================
DEFAULT_TEMPERATURE = 0.7
MAX_RESPONSE_TOKENS = 4096
STREAM_RESPONSES = True

# ============================================================================
# TTS CONFIGURATION
# ============================================================================
TTS_ENABLED = os.getenv("TTS_ENABLED", "false").lower() == "true"
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")

# ============================================================================
# LOGGING
# ============================================================================
LOG_CONVERSATIONS = True
LOG_METRICS = True
LOG_TOOL_CALLS = True
LOG_DIR = "data/logs"
METRICS_FILE = "data/logs/metrics_state.json"
PERSONA_DIR = "prompts/personas"  # Directory containing persona YAML files

# ============================================================================
# WEB SERVER
# ============================================================================
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000
WEB_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# ============================================================================
# FEATURE FLAGS (Simplified)
# ============================================================================
ENABLE_KNOWLEDGE_GRAPH = True
ENABLE_FACT_EXTRACTION = True
ENABLE_TOOL_CALLING = True
ENABLE_VISION = True
ENABLE_COMPOUND = False  # Disabled: V5+ uses native tool calling
ENABLE_AUTO_TOOLS = True  # Auto-detect when tools are needed
ENABLE_STRUCTURED_FACTS = True  # Use structured outputs for fact extraction
ENABLE_GROQ_BUILTINS = True  # Allow 120B built-in tools (web/code/browse) alongside custom tools
ENABLE_COMPUTER_USE = False  # Shelved: ComputerAgent unwired in Phase 5

# Model roles mapping (V4 architecture)
MODEL_ROLES = {
    "primary": PRIMARY_MODEL,      # Decisions, synthesis, personality  
    "chat": PRIMARY_MODEL,         # Casual conversation
    "tools": TOOLS_MODEL,          # Tool execution (Scout for now; Planner uses 120B)
    "tools_fast": TOOLS_MODEL_FAST,  # Future: pure execution
    "vision": VISION_MODEL,        # Image analysis
    "compound": "DISABLED",        # Explicitly disabled
    "memory": MEMORY_PROCESSING_MODEL,  # Memory operations
    "memory_processing": MEMORY_PROCESSING_MODEL,
    "memory_fast": MEMORY_FAST_MODEL,
    "memory_local": MEMORY_LOCAL_MODEL,
    "summary": MEMORY_PROCESSING_MODEL,      # Summarization
    "facts": MEMORY_PROCESSING_MODEL,        # Fact extraction
    "insight": MEMORY_PROCESSING_MODEL,      # Analysis/insight
    "embeddings": EMBEDDING_MODEL,
}

# Feature flag: Use 8B for tool execution instead of Scout
# Set to True to enable V4 tool routing (120B decides, 8B executes)
# USE_FAST_TOOL_EXECUTOR = False  # REMOVED DUPLICATE DEFINITION

# V5: Compound disabled - 120B has built-in search

# ============================================================================
# COMPLEXITY CLASSIFICATION - Simplified (no escalation)
# ============================================================================
# Tool trigger keywords - these should always check tools regardless of length
TOOL_TRIGGERS = [
    "time", "weather", "calculate", "search", "find", "look up",
    "what is", "who is", "where is", "wikipedia", "read", "file",
    "screen", "look at", "pdf", "document",
    "open", "launch", "click", "type", "scroll", "press",
]

def needs_tools(query: str) -> bool:
    """Check if query likely needs tool access."""
    query_lower = query.lower()
    return any(trigger in query_lower for trigger in TOOL_TRIGGERS)

def classify_complexity(query: str) -> int:
    """
    Classify query complexity (0-2).
    This is simplified - no longer used for model escalation.
    0 = casual chat (no tools needed)
    1 = normal query (may need tools)
    2 = complex/analytical
    """
    query_lower = query.lower()
    
    # Tool triggers always get complexity >= 1 (so tools are checked)
    if needs_tools(query_lower):
        return 1
    
    # Casual indicators
    # Normalize punctuation for better matching
    clean_query = query_lower.replace(',', ' ').replace('.', ' ').replace('!', ' ').strip()
    casual_patterns = ["hi", "hello", "hey", "sup", "yo", "what's up", "how are you", "thanks", "ok", "yeah", "yep", "nope", "lol", "haha", "test", "testing"]
    
    # Check for exact matches or starts-with
    if any(clean_query == p or clean_query.startswith(p + " ") for p in casual_patterns):
        return 0
        
    # Check for "test message" specifically
    if "test message" in query_lower or "verify the server" in query_lower:
        return 0
        
    if len(query) < 20:
        return 0
    
    # Complex indicators
    complex_patterns = ["explain", "analyze", "compare", "evaluate", "synthesize", "critique", "implement", "design", "architecture", "algorithm"]
    if any(p in query_lower for p in complex_patterns):
        return 2
    
    return 1
