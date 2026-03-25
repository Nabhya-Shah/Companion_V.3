"""
Local LLM Interface - Run models locally on your GPU via vLLM.

vLLM provides:
- 2x faster inference via PagedAttention
- OpenAI-compatible API at http://localhost:8000
- Runs in WSL2 with full CUDA support

Default Model: Qwen/Qwen2.5-3B-Instruct (can be changed)

To start vLLM server (in WSL):
    source ~/vllm-env/bin/activate
    python -m vllm.entrypoints.openai.api_server \
        --model Qwen/Qwen2.5-3B-Instruct \
        --host 0.0.0.0 --port 8000
"""

import os
import logging
import requests
import json
from typing import Optional, Generator, List, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class VLLMClientWrapper:
    """
    A wrapper for vLLM that mimics the OpenAI/Groq client interface.
    vLLM provides OpenAI-compatible endpoints at /v1/chat/completions.
    """
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.chat = self.Chat(base_url)
        
    class Chat:
        def __init__(self, base_url):
            self.completions = self.Completions(base_url)
            
        class Completions:
            def __init__(self, base_url):
                self.base_url = base_url
                
            def create(self, model: str, messages: List[Dict], tools=None, tool_choice=None, **kwargs):
                """Create a chat completion using vLLM's OpenAI-compatible API."""
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_tokens": kwargs.get("max_tokens", 1024),
                    "top_p": kwargs.get("top_p", 0.9),
                }
                
                if tools:
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
                        logger.error(f"vLLM Error {response.status_code}: {response.text}")
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    # Convert dict to object-like structure for compatibility
                    return self._dict_to_obj(data)
                    
                except requests.exceptions.ConnectionError:
                    logger.error("vLLM server not running. Start it with: wsl -e bash -c 'source ~/vllm-env/bin/activate && python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-3B-Instruct --host 0.0.0.0 --port 8000'")
                    raise
                except Exception as e:
                    logger.error(f"vLLM client error: {e}")
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
    def list_models(self) -> List[str]:
        """List available models."""
        pass


class VLLMBackend(LocalLLMBackend):
    """vLLM backend - fast inference via WSL2."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._available = None
        self._current_model = None
    
    def is_available(self) -> bool:
        """Check if vLLM server is running."""
        if self._available is not None:
            return self._available
        
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            if response.status_code == 200:
                self._available = True
                # Cache the current model name
                data = response.json()
                if data.get("data"):
                    self._current_model = data["data"][0].get("id")
            else:
                self._available = False
        except Exception:
            self._available = False
        
        return self._available
    
    def get_current_model(self) -> Optional[str]:
        """Get the currently loaded model name."""
        if self._current_model:
            return self._current_model
        
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    self._current_model = data["data"][0].get("id")
                    return self._current_model
        except Exception:
            pass
        return None
    
    def generate(self, prompt: str, model: str = None) -> str:
        """Generate response using vLLM."""
        model = model or self.get_current_model() or "Qwen/Qwen2.5-3B-Instruct"
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "max_tokens": 1024,
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"vLLM generate error: {e}")
            raise
    
    def generate_streaming(self, prompt: str, model: str = None) -> Generator[str, None, None]:
        """Stream response tokens."""
        model = model or self.get_current_model() or "Qwen/Qwen2.5-3B-Instruct"
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "max_tokens": 1024,
                },
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        json_str = line_str[6:]
                        if json_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(json_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"vLLM streaming error: {e}")
            raise
    
    def generate_with_image(self, prompt: str, image_path: str, model: str = None) -> str:
        """Generate response with image using vision model.
        
        Note: vLLM supports some vision models. If no vision model is loaded,
        this will fall back to text-only generation.
        """
        import base64
        
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        model = model or self.get_current_model()
        
        # Check if model supports vision (contains 'vision' or 'vl' in name)
        if model and any(x in model.lower() for x in ["vision", "vl", "llava", "qwen-vl"]):
            try:
                response = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                            ]
                        }],
                        "stream": False,
                        "max_tokens": 512,
                    },
                    timeout=120
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"vLLM vision error: {e}")
                raise
        else:
            logger.warning(f"Model {model} may not support vision. Falling back to text-only.")
            return self.generate(f"[Image attached] {prompt}", model)
    
    def list_models(self) -> List[str]:
        """List models available on the vLLM server."""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.error(f"vLLM list models error: {e}")
            return []


class LocalLLM:
    """
    Main interface for local LLM operations.
    
    Uses vLLM backend for fast GPU inference.
    """
    
    # Default models for different tasks
    DEFAULT_MODELS = {
        "text": None,  # Uses whatever model is loaded in vLLM
        "reasoning": None,
        "vision": None,  # Need to load a vision model separately
        "code": None,
    }
    
    def __init__(self):
        self.backend: Optional[LocalLLMBackend] = None
        self._init_backend()
    
    def _init_backend(self):
        """Initialize the vLLM backend."""
        vllm = VLLMBackend()
        if vllm.is_available():
            self.backend = vllm
            model = vllm.get_current_model()
            logger.info(f"LocalLLM: Using vLLM backend with model: {model}")
            return
    
    def is_available(self) -> bool:
        """Check if vLLM backend is available."""
        return self.backend is not None and self.backend.is_available()
    
    def get_client(self) -> VLLMClientWrapper:
        """Get an OpenAI-compatible client wrapper for tool calling compatibility.
        
        Returns:
            VLLMClientWrapper that mimics OpenAI/Groq client interface
        """
        return VLLMClientWrapper()
    
    def generate(self, prompt: str, task: str = "text", model: str = None) -> str:
        """
        Generate a response using vLLM.
        
        Args:
            prompt: The prompt to send
            task: Task type (text, reasoning, vision, code) - currently ignored
            model: Override model name (uses loaded model if None)
            
        Returns:
            Generated response text
        """
        if not self.is_available():
            raise RuntimeError("vLLM server not available. Start a compatible local model server.")
        
        return self.backend.generate(prompt, model)
    
    def generate_streaming(self, prompt: str, task: str = "text", model: str = None) -> Generator[str, None, None]:
        """Stream response tokens."""
        if not self.is_available():
            raise RuntimeError("vLLM server not available. Start a compatible local model server.")
        
        if isinstance(self.backend, VLLMBackend):
            yield from self.backend.generate_streaming(prompt, model)
        else:
            yield self.backend.generate(prompt, model)
    
    def analyze_image(self, prompt: str, image_path: str, model: str = None) -> str:
        """
        Analyze an image using vision model.
        
        Note: Requires a vision-capable model to be loaded in vLLM.
        """
        if not self.is_available():
            raise RuntimeError("vLLM server not available. Start a compatible local model server.")
        
        return self.backend.generate_with_image(prompt, image_path, model)
    
    def list_models(self) -> List[str]:
        """List models loaded in vLLM server."""
        if not self.is_available():
            return []
        return self.backend.list_models()
    
    def get_current_model(self) -> Optional[str]:
        """Get the currently loaded model name."""
        if isinstance(self.backend, VLLMBackend):
            return self.backend.get_current_model()
        return None


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

# Proper OllamaBackend for native Ollama (port 11434)
class OllamaBackend(LocalLLMBackend):
    """Native Ollama backend - uses localhost:11434."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._available = None
    
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        if self._available is not None:
            return self._available
        
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    def generate(self, prompt: str, model: str = None) -> str:
        """Generate response using Ollama."""
        model = model or "qwen2.5:7b"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise
    
    def generate_with_image(self, prompt: str, image_path: str, model: str = None) -> str:
        """Generate response with image using Ollama vision model (llava)."""
        import base64
        
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        model = model or "llava:7b"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False,
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            raise
    
    def list_models(self) -> List[str]:
        """List models available in Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Ollama list models error: {e}")
            return []


# Legacy compatibility
OllamaClientWrapper = VLLMClientWrapper
