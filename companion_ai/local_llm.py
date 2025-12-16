"""
Local LLM Interface - Run models locally on your GPU.

Supports:
- Ollama (recommended - easy setup)
- llama-cpp-python (fallback)

Models optimized for RTX 5080 (16GB VRAM):
- llama3.2:8b - Fast, good instruction following
- mistral:7b - Balanced performance
- deepseek-r1:8b - Strong reasoning
- qwen2.5:14b - Best quality (may need quantization)

Vision Models:
- llava:7b - Image understanding
- moondream - Lightweight vision
"""

import os
import logging
import subprocess
from typing import Optional, Generator
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class OllamaClientWrapper:
    """
    A wrapper for Ollama that mimics the OpenAI/Groq client interface.
    Allows using Ollama with existing tool-calling logic.
    """
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url
        self.chat = self.Chat(base_url)
        
    class Chat:
        def __init__(self, base_url):
            self.completions = self.Completions(base_url)
            
        class Completions:
            def __init__(self, base_url):
                self.base_url = base_url
                
            def create(self, model, messages, tools=None, tool_choice=None, **kwargs):
                import requests
                import json
                
                # Prepare payload for Ollama /v1/chat/completions
                # NOTE: Ollama's OpenAI compatibility layer expects standard OpenAI params
                # We map 'options' only if using the native /api/chat endpoint, but for /v1/ we use standard params
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_tokens": kwargs.get("max_tokens", 1024),
                    "top_p": kwargs.get("top_p", 0.9),
                }
                
                if tools:
                    # Ensure tools are in the correct format (list of dicts)
                    # Some versions of Ollama are strict about the schema
                    payload["tools"] = tools
                    if tool_choice:
                        payload["tool_choice"] = tool_choice
                
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/chat/completions",
                        json=payload,
                        timeout=120
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Ollama Error {response.status_code}: {response.text}")
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    # Convert dict to object-like structure for compatibility
                    return self._dict_to_obj(data)
                    
                except Exception as e:
                    logger.error(f"Ollama client error: {e}")
                    raise
            
            def _dict_to_obj(self, data):
                """Convert dictionary to object with attribute access."""
                if isinstance(data, dict):
                    class Obj:
                        pass
                    obj = Obj()
                    for k, v in data.items():
                        setattr(obj, k, self._dict_to_obj(v))
                    return obj
                elif isinstance(data, list):
                    return [self._dict_to_obj(i) for i in data]
                else:
                    return data

class LocalLLMBackend(ABC):
    """Abstract base class for local LLM backends."""
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
        pass
    
    @abstractmethod
    def generate(self, prompt: str, model: str = None) -> str:
        """Generate a response from the model."""
        pass
    
    @abstractmethod
    def generate_with_image(self, prompt: str, image_path: str, model: str = None) -> str:
        """Generate a response from a vision model with an image."""
        pass
    
    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        pass


class OllamaBackend(LocalLLMBackend):
    """Ollama backend - recommended for ease of use."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._available = None
    
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        if self._available is not None:
            return self._available
        
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    def generate(self, prompt: str, model: str = "llama3.2:8b") -> str:
        """Generate response using Ollama."""
        import requests
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise
    
    def generate_streaming(self, prompt: str, model: str = "llama3.2:8b") -> Generator[str, None, None]:
        """Stream response tokens."""
        import requests
        import json
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True
                },
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]
                    if data.get("done", False):
                        break
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise
    
    def generate_with_image(self, prompt: str, image_path: str, model: str = "llava:7b") -> str:
        """Generate response with image using vision model."""
        import requests
        import base64
        
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False
                },
                timeout=120
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            raise
    
    def list_models(self) -> list[str]:
        """List installed Ollama models."""
        import requests
        
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [m["name"] for m in models]
        except Exception as e:
            logger.error(f"Ollama list models error: {e}")
            return []
    
    def pull_model(self, model: str) -> bool:
        """Pull a model from Ollama registry."""
        import requests
        
        try:
            logger.info(f"Pulling model: {model}")
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
                timeout=600  # 10 minutes for large models
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama pull error: {e}")
            return False


class LocalLLM:
    """
    Main interface for local LLM operations.
    
    Automatically selects the best available backend.
    """
    
    # Default models for different tasks
    DEFAULT_MODELS = {
        "text": "llama3.2:latest",         # Fast, good instruction following
        "reasoning": "llama3.2:latest",     # Use text model (deepseek too slow)
        "vision": "llava:13b",              # Image understanding (WINNER: 10s vs 35s/50s)
        "code": "qwen2.5-coder:7b",         # Code generation
    }
    
    def __init__(self):
        self.backend: Optional[LocalLLMBackend] = None
        self._init_backend()
    
    def _init_backend(self):
        """Initialize the best available backend."""
        # Try Ollama first (recommended)
        ollama = OllamaBackend()
        if ollama.is_available():
            self.backend = ollama
            logger.info("LocalLLM: Using Ollama backend")
            return
        
        # TODO: Add llama-cpp-python fallback
        logger.warning("LocalLLM: No backend available. Install Ollama: https://ollama.ai")
    
    def is_available(self) -> bool:
        """Check if any local LLM backend is available."""
        return self.backend is not None and self.backend.is_available()
    
    def get_client(self) -> OllamaClientWrapper:
        """Get an OpenAI-compatible client wrapper for tool calling compatibility.
        
        Returns:
            OllamaClientWrapper that mimics OpenAI/Groq client interface
        """
        return OllamaClientWrapper()
    
    def generate(self, prompt: str, task: str = "text", model: str = None) -> str:
        """
        Generate a response using local LLM.
        
        Args:
            prompt: The prompt to send
            task: Task type (text, reasoning, vision, code) - selects default model
            model: Override model name
            
        Returns:
            Generated response text
        """
        if not self.is_available():
            raise RuntimeError("No local LLM backend available. Install Ollama.")
        
        model = model or self.DEFAULT_MODELS.get(task, self.DEFAULT_MODELS["text"])
        return self.backend.generate(prompt, model)
    
    def generate_streaming(self, prompt: str, task: str = "text", model: str = None) -> Generator[str, None, None]:
        """Stream response tokens."""
        if not self.is_available():
            raise RuntimeError("No local LLM backend available. Install Ollama.")
        
        model = model or self.DEFAULT_MODELS.get(task, self.DEFAULT_MODELS["text"])
        
        if isinstance(self.backend, OllamaBackend):
            yield from self.backend.generate_streaming(prompt, model)
        else:
            # Fallback for non-streaming backends
            yield self.backend.generate(prompt, model)
    
    def analyze_image(self, prompt: str, image_path: str, model: str = None) -> str:
        """
        Analyze an image using local vision model.
        
        Args:
            prompt: What to analyze
            image_path: Path to image file
            model: Vision model to use (default: llava:7b)
            
        Returns:
            Analysis text
        """
        if not self.is_available():
            raise RuntimeError("No local LLM backend available. Install Ollama.")
        
        model = model or self.DEFAULT_MODELS["vision"]
        return self.backend.generate_with_image(prompt, image_path, model)
    
    def list_models(self) -> list[str]:
        """List available local models."""
        if not self.is_available():
            return []
        return self.backend.list_models()
    
    def ensure_model(self, model: str) -> bool:
        """
        Ensure a model is available, pulling if necessary.
        
        Args:
            model: Model name (e.g., "llama3.2:8b")
            
        Returns:
            True if model is available
        """
        if not self.is_available():
            return False
        
        models = self.list_models()
        if model in models:
            return True
        
        # Try to pull the model
        if isinstance(self.backend, OllamaBackend):
            return self.backend.pull_model(model)
        
        return False


# Singleton instance
_local_llm: Optional[LocalLLM] = None


def get_local_llm() -> LocalLLM:
    """Get the global LocalLLM instance."""
    global _local_llm
    if _local_llm is None:
        _local_llm = LocalLLM()
    return _local_llm


# Convenience functions
def local_generate(prompt: str, task: str = "text") -> str:
    """Quick local generation."""
    return get_local_llm().generate(prompt, task)


def local_analyze_image(prompt: str, image_path: str) -> str:
    """Quick local image analysis."""
    return get_local_llm().analyze_image(prompt, image_path)


def is_local_available() -> bool:
    """Check if local LLM is available."""
    return get_local_llm().is_available()
