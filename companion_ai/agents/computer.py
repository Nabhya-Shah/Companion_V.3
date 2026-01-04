import logging
import time
import json
import threading
from typing import Tuple, Optional, Dict, List

import pyautogui

# Vision manager is optional (computer use currently shelved)
try:
    from companion_ai.vision_manager import vision_manager
    VISION_AVAILABLE = True
except ImportError:
    vision_manager = None
    VISION_AVAILABLE = False

from companion_ai.core import config as core_config

# Configure logging
logger = logging.getLogger(__name__)

# Safety failsafe (move mouse to corner to abort)
pyautogui.FAILSAFE = True
# Small pause between actions
pyautogui.PAUSE = 0.5

class ComputerAgent:
    """
    Agent capable of interacting with the computer via PyAutoGUI.
    Uses VisionManager (Maverick) to locate UI elements.
    
    Philosophy: "Maverick Sees, ComputerAgent Clicks."
    """
    def __init__(self):
        self.enabled = True 
        self.safe_mode = False # If True, only log actions, don't execute
        # Tracks whether the agent has performed a recent computer action.
        # The UI banner should reflect real activity, not mere availability.
        self._last_action_ts = 0.0
        self.screen_width, self.screen_height = pyautogui.size()
        logger.info(f"ComputerAgent initialized. Screen: {self.screen_width}x{self.screen_height}. Safe Mode: {self.safe_mode}")

    def mark_action(self):
        """Mark that a computer-control action just occurred."""
        self._last_action_ts = time.time()

    def is_recently_active(self, window_seconds: float = 2.0) -> bool:
        """True if the agent acted within the last window_seconds."""
        if self.safe_mode or not self.enabled:
            return False
        return (time.time() - float(self._last_action_ts or 0.0)) <= float(window_seconds)

    def locate_element(self, element_description: str) -> Optional[Tuple[int, int]]:
        """
        Locate a UI element using Vision (LLM-based detection).
        Returns: (x, y) or None if not found.
        """
        logger.info(f"👀 Locating element: '{element_description}'")
        
        # Check if vision is available
        if not VISION_AVAILABLE or vision_manager is None:
            logger.warning("Vision not available, using hardcoded locations")
            return self._get_hardcoded_location(element_description)
        
        # Capture screen
        img = vision_manager.capture_screen(resize_dim=None)
        if not img:
            logger.error("Failed to capture screen.")
            return None
        
        # Use vision to locate element
        prompt = (
            f"Locate the center of the '{element_description}'. "
            "Return ONLY a JSON object with 'x' and 'y' integers representing "
            "the percentage coordinates (0-100) from top-left. "
            "Example: {\"x\": 50, \"y\": 50} for center of screen. "
            "If not visible, return {\"error\": \"not found\"}."
        )
        
        response_text = vision_manager.analyze_current_screen(prompt, high_detail=True)
        
        try:
            json_str = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_str)
            
            if "error" in data:
                logger.warning(f"Element '{element_description}' not found: {data['error']}")
                return self._get_hardcoded_location(element_description)
                
            pct_x = data.get("x", 0) / 100.0
            pct_y = data.get("y", 0) / 100.0
            
            real_x = int(pct_x * self.screen_width)
            real_y = int(pct_y * self.screen_height)
            
            logger.info(f"📍 Located '{element_description}' at ({real_x}, {real_y})")
            return (real_x, real_y)
            
        except Exception as e:
            logger.error(f"Vision location failed: {e}")
            return self._get_hardcoded_location(element_description)

    def _get_hardcoded_location(self, description: str) -> Optional[Tuple[int, int]]:
        """Return hardcoded coordinates for common UI elements if vision fails."""
        d = description.lower()
        
        # Windows Start Button / Search
        # Try Bottom Center (Win 11) then Bottom Left (Win 10)
        # We'll return Bottom Center for now as it's common on Win 11
        if "start" in d or "windows" in d or "search" in d:
             # Assume 1920x1080 or similar
             # Windows 11 Start is usually centered. Let's try 50px from bottom, center.
             x = int(self.screen_width / 2)
             y = self.screen_height - 20
             logger.info(f"📍 using HARDCODED location for '{description}' at ({x}, {y})")
             return (x, y)
             
        return None

    def click_element(self, description: str, double_click: bool = False) -> str:
        """Locate and click a UI element."""
        if not self.enabled:
            return "Computer Use is disabled in settings."
            
        coords = self.locate_element(description)
        if not coords:
            return f"Could not find '{description}' on screen."
            
        x, y = coords
        
        if self.safe_mode:
            # Visualize the move but don't click
            pyautogui.moveTo(x, y, duration=0.5)
            action = "Double-click" if double_click else "Click"
            return f"[SAFE MODE] Would have moved to and mapped {action} at ({x}, {y}) for '{description}'"
        
        try:
            pyautogui.moveTo(x, y, duration=0.5)
            if double_click:
                pyautogui.doubleClick()
            else:
                pyautogui.click()
            return f"Clicked '{description}' at ({x}, {y})."
        except Exception as e:
            return f"Failed to click: {e}"

    def set_active_status(self, active: bool):
        """Toggle active status indicator."""
        # In a real app, this would push to the frontend.
        # For now, we print a visible banner to the console.
        if active:
            print("\n" + "="*40)
            print(" 🚨 COMPUTER AGENT ACTIVE - HANDS OFF 🚨")
            print("="*40 + "\n")
        else:
            print("\n" + "-"*40)
            print(" ✅ Computer Agent Finished.")
            print("-"*40 + "\n")

    def type_text(self, text: str, enter: bool = False) -> str:
        """Type text at current cursor location."""
        if not self.enabled:
            return "Computer Use is disabled."
            
        if self.safe_mode:
            return f"[SAFE MODE] Would have typed: '{text}'" + (" [ENTER]" if enter else "")
            
        try:
            pyautogui.write(text, interval=0.05)
            if enter:
                pyautogui.press('enter')
            return f"Typed: '{text}'"
        except Exception as e:
            return f"Failed to type: {e}"
    
    def scroll(self, direction: str, amount: int = 500) -> str:
        """Scroll 'up' or 'down'."""
        if not self.enabled: return "Computer Use disabled."
        
        clicks = amount if direction == 'up' else -amount
        
        if self.safe_mode:
            return f"[SAFE MODE] Would scroll {direction} by {amount}"
            
        try:
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll failed: {e}"

    def press_key(self, key_name: str) -> str:
        """Press a specific key (e.g., 'win', 'enter', 'esc') or combination ('ctrl+esc')."""
        if not self.enabled: return "Computer Use disabled."
        
        if self.safe_mode:
            return f"[SAFE MODE] Would press key: '{key_name}'"
            
        try:
            if '+' in key_name:
                # Handle combination "ctrl+esc"
                keys = key_name.split('+')
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key_name)
            return f"Pressed key: '{key_name}'"
        except Exception as e:
            return f"Failed to press key: {e}"

    def launch_app(self, app_name: str) -> str:
        """Launch an application reliably using Windows Run (Win+R)."""
        if not self.enabled: return "Computer Use disabled."
        
        step_desc = f"Win+R -> Type '{app_name}' -> Enter"
        
        if self.safe_mode:
            return f"[SAFE MODE] Would launch app via: {step_desc}"
            
        try:
            # 1. Open Run dialog
            pyautogui.hotkey('win', 'r')
            time.sleep(0.5) # Wait for dialog
            
            # 2. Type App Name
            pyautogui.write(app_name)
            time.sleep(0.1)
            
            # 3. Enter
            pyautogui.press('enter')
            
            return f"Launched '{app_name}' via Run command."
        except Exception as e:
            return f"Failed to launch app: {e}"

# Global instance
computer_agent = ComputerAgent()
