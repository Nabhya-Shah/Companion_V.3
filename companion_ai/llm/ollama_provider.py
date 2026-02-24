# companion_ai/llm/ollama_provider.py
"""Local Ollama LLM provider — embeddings, text generation, model config."""

import os
import logging
import requests

from companion_ai.llm.token_tracker import log_tokens

logger = logging.getLogger(__name__)

# ============================================================================
# Local Model Clients (Native Ollama)
# ============================================================================
# All local models now run through native Ollama for stability and simplicity.
# No Docker containers needed - just run 'ollama serve' and pull models.

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Models available through Ollama
OLLAMA_TEXT_MODEL = "qwen2.5:7b"        # Mini-orchestrator for loop iterations
OLLAMA_VISION_MODEL = "llava:7b"         # Vision analysis
OLLAMA_EMBED_MODEL = "nomic-embed-text"  # Embeddings for semantic search
OLLAMA_CODE_MODEL = "qwen2.5-coder:32b"  # Code generation (on-demand)


# ============================================================================
# Ollama Client (for Embeddings and On-Demand Models)
# ============================================================================

def get_embedding(text: str) -> list:
    """Get embedding vector using Ollama's nomic-embed-text model."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": OLLAMA_EMBED_MODEL, "input": text},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("embeddings", [[]])[0]
        else:
            logger.error(f"Ollama embed failed: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []


def get_embeddings_batch(texts: list) -> list:
    """Get embeddings for multiple texts."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": OLLAMA_EMBED_MODEL, "input": texts},
            timeout=60
        )
        if response.status_code == 200:
            return response.json().get("embeddings", [])
        return []
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        return []


def generate_local_response(prompt: str, system_prompt: str = None, max_tokens: int = 1024) -> str:
    """Generate a response using the local Ollama text model.

    Uses Ollama for text (more memory efficient) instead of vLLM.
    """
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_TEXT_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7
                }
            },
            timeout=120
        )

        if response.status_code == 200:
            data = response.json()
            content = data.get("message", {}).get("content", "")

            # Log tokens if available
            if "eval_count" in data:
                log_tokens(
                    OLLAMA_TEXT_MODEL,
                    data.get("prompt_eval_count", 0),
                    data.get("eval_count", 0),
                    "ollama_local"
                )

            return content
        else:
            logger.error(f"Ollama text generation failed: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Local generation failed: {e}")
        return None
