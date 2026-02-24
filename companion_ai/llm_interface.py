# companion_ai/llm_interface.py   backwards-compatibility shim
"""All real code now lives in companion_ai.llm.* sub-modules.

This file re-exports every public symbol so that existing
``from companion_ai.llm_interface import X`` statements keep working.
"""

# --- Token tracking ---
from companion_ai.llm.token_tracker import (          # noqa: F401
    reset_last_request_tokens,
    get_last_token_usage,
    log_tokens_step,
    log_tokens,
    get_token_stats,
    reset_token_stats,
)

# --- Groq provider ---
from companion_ai.llm.groq_provider import (          # noqa: F401
    sanitize_output,
    get_groq_client,
    groq_client,
    groq_tool_client,
    groq_memory_client,
    generate_model_response_with_tools,
    generate_model_response,
    generate_model_response_streaming,
    generate_groq_response,
)

# --- Ollama provider ---
from companion_ai.llm.ollama_provider import (         # noqa: F401
    get_embedding,
    get_embeddings_batch,
    generate_local_response,
    OLLAMA_URL,
    OLLAMA_TEXT_MODEL,
    OLLAMA_VISION_MODEL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_CODE_MODEL,
)

# --- Router (high-level) ---
from companion_ai.llm.router import (                 # noqa: F401
    generate_response,
    generate_response_streaming,
)

# --- Memory extraction ---
from companion_ai.llm.memory_extraction import (       # noqa: F401
    generate_summary,
    extract_profile_facts,
    generate_insight,
)
