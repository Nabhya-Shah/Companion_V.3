import os
import time
import threading
import base64
import io
import logging
import collections
import tempfile
from datetime import datetime
from typing import Optional, Deque, List, Dict

import mss
from PIL import Image
from groq import Groq

from companion_ai.core.config import GROQ_VISION_API_KEY, VISION_MODEL

# Configure logging
logger = logging.getLogger(__name__)

class VisionManager:
    """
    Manages screen capture, visual memory, and vision model interactions.
    Supports both 'Active' (on-demand) and 'Watcher' (background summary) modes.
    
    Uses Llama 4 Maverick for vision tasks with a dedicated API key.
    """
    def __init__(self):
        # Use LOCAL vision by default (saves Groq tokens, llava:13b is installed)
        self.use_local_vision = os.getenv("USE_LOCAL_VISION", "1").strip().lower() in {"1", "true", "yes", "on"}
        self.local_vision_model = os.getenv("LOCAL_VISION_MODEL", "llava:7b")
        self._local_backend = None

        if self.use_local_vision:
            try:
                from companion_ai.local_llm import OllamaBackend
                backend = OllamaBackend()
                if backend.is_available():
                    self._local_backend = backend
                    logger.info(f"VisionManager using LOCAL Ollama vision model: {self.local_vision_model}")
                else:
                    logger.warning("VisionManager: USE_LOCAL_VISION enabled but Ollama not available; falling back to Groq")
            except Exception as e:
                logger.warning(f"VisionManager: local vision init failed; falling back to Groq: {e}")

        # Use dedicated vision API key (falls back to main key in config)
        self.api_key = GROQ_VISION_API_KEY
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        
        # Configuration
        self.watcher_enabled = False
        self.watcher_interval = 10.0  # Seconds between summary checks
        self.change_threshold = 5.0   # Percent of pixels changed to trigger update
        self.history_size = 20        # Number of summary entries to keep
        
        # State
        self.visual_log: Deque[Dict] = collections.deque(maxlen=self.history_size)
        self.last_image: Optional[Image.Image] = None
        self.watcher_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Unified vision model - Llama 4 Maverick for all vision tasks
        self.vision_model = VISION_MODEL
        
        logger.info(f"VisionManager initialized with model: {self.vision_model}")

    def _run_local_vision(self, prompt: str, img: Image.Image) -> str:
        """Run local Ollama vision model on an in-memory PIL image."""
        if not self._local_backend:
            return "Local vision unavailable"

        # Ollama backend expects a file path for now.
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
                img.save(tmp, format="JPEG", quality=70)
            return self._local_backend.generate_with_image(prompt, tmp_path, model=self.local_vision_model)
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def start_watcher(self):
        """Start the background watcher thread."""
        if self.watcher_enabled:
            return
        
        self.watcher_enabled = True
        self.stop_event.clear()
        self.watcher_thread = threading.Thread(target=self._watcher_loop, daemon=True)
        self.watcher_thread.start()
        logger.info("Visual Watcher started")

    def stop_watcher(self):
        """Stop the background watcher thread."""
        self.watcher_enabled = False
        self.stop_event.set()
        if self.watcher_thread:
            self.watcher_thread.join(timeout=2.0)
        logger.info("Visual Watcher stopped")

    def capture_screen(self, resize_dim: int = 768) -> Image.Image:
        """Capture current screen and return PIL Image."""
        # Use context manager for thread safety
        with mss.mss() as sct:
            # Capture primary monitor
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Resize for efficiency
            if resize_dim:
                img.thumbnail((resize_dim, resize_dim))
            
            return img

    def _image_to_base64(self, img: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def _calculate_diff(self, img1: Image.Image, img2: Image.Image) -> float:
        """Calculate percentage difference between two images."""
        if not img1 or not img2:
            return 100.0
        
        # Ensure same size
        if img1.size != img2.size:
            return 100.0
            
        # Simple histogram comparison (fast)
        h1 = img1.histogram()
        h2 = img2.histogram()
        
        diff = sum(abs(a - b) for a, b in zip(h1, h2))
        # Normalize roughly (this is a heuristic, not exact pixel diff)
        total_pixels = img1.size[0] * img1.size[1] * 3
        return (diff / total_pixels) * 100

    def _watcher_loop(self):
        """Background loop to monitor screen and log activity."""
        logger.info("Watcher loop running")
        
        while not self.stop_event.is_set():
            try:
                start_time = time.time()
                
                # 1. Capture
                current_img = self.capture_screen(resize_dim=512) # Smaller for summary
                
                # 2. Detect Change
                change_pct = 0.0
                if self.last_image:
                    change_pct = self._calculate_diff(self.last_image, current_img)
                
                # 3. If changed enough, summarize
                if not self.last_image or change_pct > self.change_threshold:
                    desc = self._generate_summary(current_img)
                    if desc:
                        entry = {
                            "timestamp": datetime.now().isoformat(),
                            "description": desc,
                            "change_pct": change_pct
                        }
                        self.visual_log.append(entry)
                        logger.info(f"Visual Log: {desc}")
                        self.last_image = current_img
                
                # 4. Sleep remainder of interval
                elapsed = time.time() - start_time
                sleep_time = max(1.0, self.watcher_interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Watcher error: {e}")
                time.sleep(5.0)

    def _generate_summary(self, img: Image.Image) -> str:
        """Generate a brief 1-sentence summary of the image using Vision API."""
        if self._local_backend:
            try:
                prompt = "Describe the active application or main screen content in 1 short sentence. Be specific."
                out = self._run_local_vision(prompt, img)
                return out.strip() if out else None
            except Exception as e:
                logger.error(f"Local vision summary failed: {e}")
                return None

        if not self.client:
            return "Vision API unavailable"
            
        try:
            b64_img = self._image_to_base64(img)
            
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe the active application or main screen content in 1 short sentence. Be specific (e.g. 'Coding in Python', 'Watching YouTube video about cats')."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_img}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=50,
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Vision summary failed: {e}")
            return None

    def get_visual_context(self) -> str:
        """Return a formatted string of recent visual history."""
        if not self.visual_log:
            return "No recent visual history."
            
        lines = ["Recent Visual History (Watcher Log):"]
        for entry in self.visual_log:
            ts = entry['timestamp'].split('T')[1][:8] # HH:MM:SS
            lines.append(f"[{ts}] {entry['description']}")
        
        return "\n".join(lines)

    def analyze_current_screen(self, prompt: str, high_detail: bool = False, low_detail: bool = False) -> str:
        """
        Active Mode: Analyze the current screen with a specific prompt.
        Uses Llama 4 Maverick for high-quality vision analysis.
        
        Args:
            prompt: User question or instruction
            high_detail: If True, use 1024px resolution (max detail).
            low_detail: If True, use 512px resolution (token saving, good for basic checks).
        """
        if self._local_backend:
            try:
                if low_detail:
                    res_dim = 512
                elif high_detail or "read" in prompt.lower() or "text" in prompt.lower():
                    res_dim = 1024
                else:
                    res_dim = 768

                img = self.capture_screen(resize_dim=res_dim)

                # Keep history short to avoid bloating local prompt.
                history = list(self.visual_log)[-5:]
                history_lines = []
                for entry in history:
                    ts = entry['timestamp'].split('T')[1][:8]
                    history_lines.append(f"[{ts}] {entry['description']}")
                history_context = "\n".join(history_lines) if history_lines else "(none)"

                full_prompt = (
                    "You are an AI agent with eyes. Analyze the screen to help the user.\n"
                    f"Recent visual history:\n{history_context}\n\n"
                    f"User question: {prompt}\n\n"
                    "Instructions:\n"
                    "1) Identify the active application and main content.\n"
                    "2) If relevant, mention visible UI elements and their state.\n"
                    "3) Be concise and direct.\n"
                )

                out = self._run_local_vision(full_prompt, img)
                return out.strip() if out else ""
            except Exception as e:
                logger.error(f"Local active vision analysis failed: {e}")
                return f"Error analyzing screen: {str(e)}"

        if not self.client:
            return "Vision API unavailable"
            
        try:
            # Dynamic resolution scaling for token optimization
            if low_detail:
                res_dim = 512 # ~512x288 (Very cheap, good for "Is Window Open?")
            elif high_detail or "read" in prompt.lower() or "text" in prompt.lower():
                res_dim = 1024 # ~1024x576 (High detail for text reading)
            else:
                res_dim = 768 # ~768x432 (Balanced default)
            
            img = self.capture_screen(resize_dim=res_dim)
            b64_img = self._image_to_base64(img)
            
            # Include visual history in the prompt context
            history_context = self.get_visual_context()
            
            # Improved System Prompt for "Computer Use" readiness
            # Explicitly asks for structured observations
            full_prompt = f"""[System: You are an AI Agent with eyes. Analyze the screen to help the user.]
Context from recent history:
{history_context}

User Question: {prompt}

Instructions:
1. Identify the active application and main content.
2. If the user asks to "click" or "type", describe the location/state of the UI element.
3. Be concise and direct.
"""
            
            start_t = time.time()
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": full_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_img}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
                temperature=0.4
            )
            
            # Log token usage if possible (not exposed easily in this method return, but logged internally)
            if hasattr(response, 'usage'):
                # We could log this to the central metrics if we imported metrics
                pass
                
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Active vision analysis failed: {e}")
            return f"Error analyzing screen: {str(e)}"

    def analyze_image_file(self, image_path: str, prompt: str = "Describe briefly.") -> str:
        """
        Analyze an uploaded image file with Maverick vision.
        OPTIMIZED: 512px images, 150 max_tokens for lower token usage.
        """
        try:
            # Load and resize image (512px saves ~50% tokens vs 1024px)
            img = Image.open(image_path)
            img = img.convert('RGB')
            img.thumbnail((768, 768))  # 768px balances quality + tokens
            
            # Skip local vision for speed
            if not self.client:
                return "Vision API unavailable - no API key configured"
            
            b64_img = self._image_to_base64(img)
            
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Briefly: {prompt}"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                            }
                        ]
                    }
                ],
                max_tokens=150,  # Optimized: 150 vs 500
                temperature=0.2
            )
            
            return response.choices[0].message.content.strip()
            
        except FileNotFoundError:
            return f"Image file not found: {image_path}"
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return f"Error analyzing image: {str(e)}"

# Global instance
vision_manager = VisionManager()
