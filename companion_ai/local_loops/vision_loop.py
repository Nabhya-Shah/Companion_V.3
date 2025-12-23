# companion_ai/local_loops/vision_loop.py
"""
Vision Loop - Analyze screen and images using local vision model.

Operations:
- describe: Describe what's on screen/in image
- find: Find specific elements on screen
- ocr: Extract text from image

Uses LLaVA 13B or similar vision model.
"""

import logging
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


@register_loop
class VisionLoop(Loop):
    """Vision analysis loop using local multimodal model."""
    
    name = "vision"
    description = "Analyze screenshots and images - describe content, find elements, extract text"
    
    system_prompts = {
        "analyzer": """You are a screen/image analyzer. Describe what you see concisely and accurately.

Focus on:
- Main content and purpose of the screen
- Key UI elements (buttons, text fields, menus)
- Any important text visible
- Overall layout and state

Be concise but thorough. Do not speculate about things you cannot see.""",

        "finder": """You are looking for specific elements on screen. 
Describe the location and state of the requested element.
If not found, say so clearly."""
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._vision_endpoint = None
    
    def _setup(self) -> None:
        """Connect to vision model."""
        self._vision_endpoint = self.config.get("vision_endpoint", "http://localhost:11434")
        logger.info(f"VisionLoop configured with endpoint: {self._vision_endpoint}")
    
    def _get_supported_operations(self) -> List[str]:
        return ["describe", "find", "ocr"]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a vision task.
        
        Task format:
            {"operation": "describe"}  # Captures current screen
            {"operation": "describe", "image_path": "/path/to/image.png"}
            {"operation": "find", "element": "submit button"}
            {"operation": "ocr"}
        """
        operation = task.get("operation")
        
        if operation == "describe":
            return await self._describe(task.get("image_path"))
        elif operation == "find":
            return await self._find(task.get("element", ""), task.get("image_path"))
        elif operation == "ocr":
            return await self._ocr(task.get("image_path"))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _capture_screen(self) -> Optional[str]:
        """Capture current screen and return base64 encoded image."""
        try:
            import pyautogui
            from io import BytesIO
            
            screenshot = pyautogui.screenshot()
            buffer = BytesIO()
            screenshot.save(buffer, format='PNG')
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None
    
    async def _load_image(self, image_path: Optional[str]) -> Optional[str]:
        """Load image from path or capture screen."""
        if image_path:
            try:
                path = Path(image_path)
                if path.exists():
                    with open(path, 'rb') as f:
                        return base64.b64encode(f.read()).decode('utf-8')
                else:
                    logger.error(f"Image not found: {image_path}")
                    return None
            except Exception as e:
                logger.error(f"Failed to load image: {e}")
                return None
        else:
            return await self._capture_screen()
    
    async def _call_vision_model(self, image_b64: str, prompt: str) -> Optional[str]:
        """Call Ollama llava vision model with image."""
        import requests
        
        try:
            ollama_url = self._vision_endpoint or "http://localhost:11434"
            
            logger.info("Calling Ollama llava:7b for vision analysis")
            
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": "llava:7b",
                    "prompt": prompt,
                    "images": [image_b64],  # Ollama expects base64 images in 'images' array
                    "stream": False,
                    "options": {
                        "num_predict": 512,
                        "temperature": 0.1
                    }
                },
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                logger.error(f"Ollama vision call failed: {response.status_code}")
                return None
            
        except Exception as e:
            logger.error(f"Vision model call failed: {e}")
            return None
    
    async def _describe(self, image_path: Optional[str] = None) -> LoopResult:
        """Describe screen or image content."""
        try:
            image_b64 = await self._load_image(image_path)
            if not image_b64:
                return LoopResult.failure("Failed to capture/load image")
            
            description = await self._call_vision_model(image_b64, self.get_system_prompt("analyzer"))
            
            if description:
                return LoopResult.success(
                    data={"description": description},
                    operation="describe"
                )
            else:
                return LoopResult.failure("Vision model returned no description")
            
        except Exception as e:
            logger.error(f"Vision describe failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _find(self, element: str, image_path: Optional[str] = None) -> LoopResult:
        """Find a specific element on screen."""
        if not element:
            return LoopResult.failure("No element specified to find")
        
        try:
            image_b64 = await self._load_image(image_path)
            if not image_b64:
                return LoopResult.failure("Failed to capture/load image")
            
            prompt = f"{self.get_system_prompt('finder')}\n\nFind the element: '{element}'. Return coordinates [x, y] or 'Not found'."
            result = await self._call_vision_model(image_b64, prompt)
            
            # TODO: Parse coordinates from result
            logger.info(f"Vision find result: {result}")
            
            return LoopResult.success(
                data={"found": True if result and "Not found" not in result else False, "raw_result": result},
                operation="find"
            )
        except Exception as e:
            logger.error(f"Vision find failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _ocr(self, image_path: Optional[str] = None) -> LoopResult:
        """Extract text from screen/image."""
        try:
            image_b64 = await self._load_image(image_path)
            if not image_b64:
                return LoopResult.failure("Failed to capture/load image")
            
            prompt = "Extract all visible text from this image. Output only the text, observing layout if possible."
            text = await self._call_vision_model(image_b64, prompt)
            
            return LoopResult.success(
                data={"text": text or ""},
                operation="ocr"
            )
        except Exception as e:
            logger.error(f"Vision OCR failed: {e}")
            return LoopResult.failure(str(e))
