# companion_ai/local_loops/vision_loop.py
"""
Vision Loop - Analyze images using Groq Maverick (cloud).

Operations:
- describe: Describe uploaded image
- analyze: Detailed analysis of image

Uses Llama 4 Maverick via Groq for reliable, fast vision.
Optimized for low token usage.
"""

import logging
import base64
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


@register_loop
class VisionLoop(Loop):
    """Vision analysis loop using Groq Maverick (cloud)."""
    
    name = "vision"
    description = "Analyze images with Maverick - fast cloud vision"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._client = None
        self._model = "meta-llama/llama-4-maverick-17b-128e-instruct"
    
    def _setup(self) -> None:
        """Initialize Groq client for vision."""
        from companion_ai.core.config import GROQ_VISION_API_KEY
        if GROQ_VISION_API_KEY:
            from groq import Groq
            self._client = Groq(api_key=GROQ_VISION_API_KEY)
            logger.info("VisionLoop: Groq Maverick client ready")
        else:
            logger.warning("VisionLoop: No GROQ_VISION_API_KEY, vision disabled")
    
    def _get_supported_operations(self) -> List[str]:
        return ["describe", "analyze"]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a vision task.
        
        Task format:
            {"operation": "describe", "image_path": "/path/to/image.png"}
            {"operation": "analyze", "image_path": "...", "prompt": "What color is..."}
        """
        if not self._client:
            return LoopResult.failure("Vision API not configured")
        
        operation = task.get("operation", "describe")
        image_path = task.get("image_path")
        prompt = task.get("prompt", "Describe this image briefly.")
        
        if not image_path:
            return LoopResult.failure("No image_path provided")
        
        return await self._analyze_image(image_path, prompt, operation)
    
    async def _analyze_image(self, image_path: str, prompt: str, operation: str) -> LoopResult:
        """Analyze image with Groq Maverick (optimized for low tokens)."""
        import time
        start_time = time.time()
        
        try:
            # Load and encode image
            path = Path(image_path)
            if not path.exists():
                return LoopResult.failure(f"Image not found: {image_path}")
            
            # Resize image to reduce tokens (512px max)
            from PIL import Image
            import io
            
            img = Image.open(path)
            img = img.convert('RGB')
            img.thumbnail((768, 768))  # 768px balances quality + tokens
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=90)  # Higher quality for text
            image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Short, focused prompt for efficiency
            system_prompt = "Describe briefly in 1-2 sentences."
            
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{system_prompt} {prompt}"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                            }
                        ]
                    }
                ],
                max_tokens=150,  # Short responses save tokens
                temperature=0.2
            )
            
            description = response.choices[0].message.content.strip()
            elapsed = int((time.time() - start_time) * 1000)
            
            # Token tracking
            tokens_used = {
                "input": response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                "output": response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                "ms": elapsed,
                "model": "maverick"
            }
            
            logger.info(f"Vision analysis: {tokens_used['input']+tokens_used['output']} tokens, {elapsed}ms")
            
            return LoopResult.success(
                data={"description": description, "tokens": tokens_used},
                operation=operation
            )
            
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return LoopResult.failure(str(e))
