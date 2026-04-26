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
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))
OLLAMA_CODE_MODEL = "qwen2.5-coder:32b"  # Code generation (on-demand)


def _embedding_model_candidates() -> list[str]:
    """Return ordered embedding model candidates for resilient local installs."""
    ordered = [
        OLLAMA_EMBED_MODEL,
        os.getenv("EMBEDDING_MODEL", "").strip(),
        "qwen3-embedding:4b",
        "embeddinggemma:300m",
        "nomic-embed-text",
    ]
    seen = set()
    out = []
    for item in ordered:
        model = str(item or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        out.append(model)
    return out


def _post_embed(input_payload, timeout: int) -> tuple[list, str | None]:
    """Try embedding models in order and return (embeddings, model_used)."""
    last_error = "unknown"
    for model in _embedding_model_candidates():
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": model, "input": input_payload},
                timeout=timeout,
            )
            if response.status_code != 200:
                last_error = f"{model}: HTTP {response.status_code}"
                continue
            data = response.json()
            embeddings = data.get("embeddings", [])
            if isinstance(embeddings, list) and embeddings:
                return embeddings, model
            last_error = f"{model}: empty embeddings"
        except Exception as e:
            last_error = f"{model}: {e}"

    logger.error(f"Ollama embed failed after trying candidates: {last_error}")
    return [], None


# ============================================================================
# Ollama Client (for Embeddings and On-Demand Models)
# ============================================================================

def get_embedding(text: str) -> list:
    """Get embedding vector using Ollama's nomic-embed-text model."""
    try:
        embeddings, model_used = _post_embed(text, timeout=30)
        if embeddings:
            if model_used and model_used != OLLAMA_EMBED_MODEL:
                logger.info(f"Ollama embed fallback used model={model_used}")
            return embeddings[0] if embeddings[0] else []
        else:
            return []
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []


def get_embeddings_batch(texts: list) -> list:
    """Get embeddings for multiple texts."""
    try:
        embeddings, model_used = _post_embed(texts, timeout=60)
        if embeddings:
            if model_used and model_used != OLLAMA_EMBED_MODEL:
                logger.info(f"Ollama batch embed fallback used model={model_used}")
            return embeddings
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
                "think": False,
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
