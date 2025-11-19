import os
import time
import threading
import base64
import io
import logging
import collections
from datetime import datetime
from typing import Optional, Deque, List, Dict

import mss
from PIL import Image
from groq import Groq

# Configure logging
logger = logging.getLogger(__name__)

class VisionManager:
    """
    Manages screen capture, visual memory, and vision model interactions.
    Supports both 'Active' (on-demand) and 'Watcher' (background summary) modes.
    """
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
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
        # self.sct = mss.mss() # Removed: mss is not thread-safe to share
        
        # Models
        self.fast_model = "llama-3.2-11b-vision-preview"  # For watcher/summary
        self.detail_model = "llama-3.2-90b-vision-preview" # For active queries
        
        logger.info("VisionManager initialized")

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
        if not self.client:
            return "Vision API unavailable"
            
        try:
            b64_img = self._image_to_base64(img)
            
            response = self.client.chat.completions.create(
                model=self.fast_model,
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

    def analyze_current_screen(self, prompt: str) -> str:
        """
        Active Mode: Analyze the current screen with a specific prompt.
        Uses the higher quality model.
        """
        if not self.client:
            return "Vision API unavailable"
            
        try:
            img = self.capture_screen(resize_dim=1024) # Higher res for active query
            b64_img = self._image_to_base64(img)
            
            # Include visual history in the prompt context
            history_context = self.get_visual_context()
            
            full_prompt = f"""Context from recent screen history:
{history_context}

User Question: {prompt}
"""
            
            response = self.client.chat.completions.create(
                model=self.detail_model,
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
                temperature=0.6
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Active vision analysis failed: {e}")
            return f"Error analyzing screen: {str(e)}"

# Global instance
vision_manager = VisionManager()
