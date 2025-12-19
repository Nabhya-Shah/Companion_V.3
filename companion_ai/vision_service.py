"""
Vision Module - InternVL and VLM Support for vLLM.

Supports vision-language models through vLLM's OpenAI-compatible API.
Recommended models (in order of preference):
1. InternVL3.5-8B (SOTA for vision benchmarks)
2. Qwen2.5-VL-7B-Instruct (Better vLLM integration)

Note: Vision models require separate vLLM server instance with VLM support.
"""

import os
import base64
import logging
import requests
from typing import Optional, Union, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VisionResult:
    """Result from vision model inference."""
    description: str
    model: str
    tokens_used: int = 0


class VisionService:
    """
    Vision-Language Model service using vLLM's OpenAI-compatible API.
    
    Supports image analysis via chat completions with image content.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8001",  # Separate port for VLM
        model: str = "OpenGVLab/InternVL3-8B",
        timeout: int = 120
    ):
        """
        Initialize vision service.
        
        Args:
            base_url: vLLM server URL (default: localhost:8001 for VLM)
            model: Vision model name
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._available = None
    
    def is_available(self) -> bool:
        """Check if vision server is running."""
        if self._available is not None:
            return self._available
        
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _get_mime_type(self, image_path: str) -> str:
        """Get MIME type from file extension."""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        return mime_types.get(ext, "image/jpeg")
    
    def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe this image in detail.",
        max_tokens: int = 512
    ) -> VisionResult:
        """
        Analyze an image using the vision model.
        
        Args:
            image_path: Path to the image file
            prompt: Question or instruction about the image
            max_tokens: Maximum response tokens
            
        Returns:
            VisionResult with description
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Encode image
        image_data = self._encode_image(image_path)
        mime_type = self._get_mime_type(image_path)
        
        # Build message with image
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }
                }
            ]
        }]
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)
            
            return VisionResult(
                description=content,
                model=self.model,
                tokens_used=tokens
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"Vision server not available at {self.base_url}")
            raise RuntimeError(f"Vision server not running at {self.base_url}")
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            raise
    
    def describe_screen(
        self,
        screenshot_path: str,
        task: str = "general"
    ) -> VisionResult:
        """
        Describe a screenshot for various tasks.
        
        Args:
            screenshot_path: Path to screenshot
            task: Type of analysis ('general', 'ui', 'document', 'code')
            
        Returns:
            VisionResult with description
        """
        prompts = {
            "general": "Describe what you see in this screenshot.",
            "ui": "Describe the user interface elements and layout in this screenshot. List the main buttons, menus, and interactive elements.",
            "document": "Extract and summarize the text content from this document screenshot.",
            "code": "Analyze this code screenshot. Describe the programming language, structure, and what the code does."
        }
        
        prompt = prompts.get(task, prompts["general"])
        return self.analyze_image(screenshot_path, prompt)
    
    def answer_question(
        self,
        image_path: str,
        question: str
    ) -> VisionResult:
        """
        Answer a question about an image.
        
        Args:
            image_path: Path to image
            question: Question about the image
            
        Returns:
            VisionResult with answer
        """
        return self.analyze_image(image_path, question, max_tokens=256)


# Singleton instance
_vision_service: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    """Get the global vision service instance."""
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service


def is_vision_available() -> bool:
    """Check if vision service is available."""
    return get_vision_service().is_available()


def analyze_image(image_path: str, prompt: str = "Describe this image.") -> str:
    """Quick image analysis."""
    try:
        result = get_vision_service().analyze_image(image_path, prompt)
        return result.description
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        return f"Error: {e}"


# Instructions for starting vision server with InternVL
VISION_SERVER_INSTRUCTIONS = """
To start the vision server with InternVL3.5-8B:

1. Open a new WSL terminal
2. Run:
   source ~/vllm-env/bin/activate
   python -m vllm.entrypoints.openai.api_server \\
       --model OpenGVLab/InternVL3-8B \\
       --host 0.0.0.0 --port 8001 \\
       --gpu-memory-utilization 0.9

Note: You may need to run text and vision models on different GPUs
or run them at different times due to VRAM constraints.

Alternative (smaller model):
   --model Qwen/Qwen2.5-VL-7B-Instruct
"""


if __name__ == "__main__":
    print("Vision Service Module")
    print("=" * 50)
    print(VISION_SERVER_INSTRUCTIONS)
