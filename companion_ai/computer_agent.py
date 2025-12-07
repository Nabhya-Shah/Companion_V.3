import logging
import time
import json
import threading
from typing import Tuple, Optional, Dict, List

import pyautogui
from companion_ai.vision_manager import vision_manager
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
        self.enabled = False 
        self.safe_mode = True # If True, only log actions, don't execute
        self.screen_width, self.screen_height = pyautogui.size()
        logger.info(f"ComputerAgent initialized. Screen: {self.screen_width}x{self.screen_height}. Safe Mode: {self.safe_mode}")

    def locate_element(self, element_description: str) -> Optional[Tuple[int, int]]:
        """
        Locate a UI element using OmniParser (SOTA) or fallback to Maverick Vision.
        Returns: (x, y) or None if not found.
        """
        logger.info(f"👀 locating element: '{element_description}'")
        
        # 0. Capture screen regardless of method
        # We need the full resolution image for parsing
        img = vision_manager.capture_screen(resize_dim=None) # Capture native
        if not img:
            logger.error("Failed to capture screen.")
            return None
            
        native_w, native_h = img.size
        # For OmniParser/Vision API, we might need to verify resizing needs
        # OmniParser handles resolution well, but let's base64 it
        b64_img = vision_manager._image_to_base64(img)
        
        # --- STRATEGY A: OmniParser (SOTA) ---
        from companion_ai.omni_parser_client import omni_client
        
        omni_data = omni_client.parse_screen(b64_img)
        if omni_data and "elements" in omni_data:
            logger.info("Using OmniParser results...")
            elements = omni_data["elements"]
            
            # Simple fuzzy matching (case-insensitive substring)
            # In future: use embeddings or LLM to match description to list of elements
            target = element_description.lower()
            best_match = None
            
            for el in elements:
                content = el.get("content", "").lower()
                if not content: continue
                
                # Check for direct containment
                if target in content or content in target:
                     best_match = el
                     break
            
            if not best_match:
                # Log what we DID see to help debug
                visible = [e.get('content', '') for e in elements[:10]]
                logger.warning(f"Target '{target}' not found in OmniParser results. Visible inputs: {visible}")
            
            if best_match:
                bbox = best_match.get("bbox", []) # [x1, y1, x2, y2]
                if len(bbox) == 4:
                    # Calculate center
                    # OmniParser coordinates are usually normalized 0-1 or absolute pixels.
                    # Assuming they are absolute pixels based on standard output, or [0-1]
                    # If they are float <= 1.0, they are relative.
                    x1, y1, x2, y2 = bbox
                    if x1 <= 1.0 and x2 <= 1.0:
                         # Normalize to screen
                         real_x = int(((x1 + x2) / 2) * self.screen_width)
                         real_y = int(((y1 + y2) / 2) * self.screen_height)
                    else:
                         # Absolute pixels (if OmniParser ran on same res)
                         # We might need to scale if the capture res differed from screen res
                         scale_x = self.screen_width / native_w
                         scale_y = self.screen_height / native_h
                         
                         center_x = (x1 + x2) / 2
                         center_y = (y1 + y2) / 2
                         
                         real_x = int(center_x * scale_x)
                         real_y = int(center_y * scale_y)
                    
                    logger.info(f"📍 OmniParser found '{best_match['content']}' at ({real_x}, {real_y})")
                    return (real_x, real_y)
        
        # --- STRATEGY B: Maverick Vision (LLM Fallback) ---
        logger.info("⚠️ OmniParser invalid/missed. Falling back to specific Vision query.")
        
        # We assume vision_manager can resize for us if needed for the LLM
        prompt = (
            f"Locate the center of the '{element_description}'. "
            "Return ONLY a JSON object with 'x' and 'y' integers representing the percentage coordinates (0-100) from top-left. "
            "Example: {\"x\": 50, \"y\": 50} for center of screen. "
            "If not visible, return {\"error\": \"not found\"}."
        )
        
        response_text = vision_manager.analyze_current_screen(prompt, high_detail=True)
        
        try:
            json_str = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_str)
            
            if "error" in data:
                logger.warning(f"Element '{element_description}' not found (Fallback): {data['error']}")
                return None
                
            pct_x = data.get("x", 0) / 100.0
            pct_y = data.get("y", 0) / 100.0
            
            real_x = int(pct_x * self.screen_width)
            real_y = int(pct_y * self.screen_height)
            
            logger.info(f"📍 Mapped '{element_description}' to ({real_x}, {real_y}) via Fallback")
            return (real_x, real_y)
            
        except Exception as e:
            logger.error(f"Fallback vision failed: {e}")
            
        # --- STRATEGY C: Hardcoded Locations (Last Resort) ---
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
