"""
Game Controller Module
Simulates keyboard and mouse input for game control
Uses pydirectinput for DirectX game compatibility
"""

import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import threading


# Try to import pydirectinput, fall back to pyautogui
try:
    import pydirectinput as pdi
    pdi.PAUSE = 0  # No delay between actions
    USING_DIRECTINPUT = True
except ImportError:
    import pyautogui as pdi
    pdi.PAUSE = 0
    USING_DIRECTINPUT = False
    print("Warning: pydirectinput not available, using pyautogui (may not work in some games)")


@dataclass
class KeyState:
    """Track state of a key"""
    key: str
    is_pressed: bool = False
    pressed_at: float = 0


class GameController:
    """
    Game input controller with multi-key support.
    Handles simultaneous key presses for gaming (WASD + shift, etc.)
    
    Usage:
        ctrl = GameController()
        
        # Simple press
        ctrl.press("w")
        
        # Hold keys
        ctrl.key_down("w")
        ctrl.key_down("shift")  # Now sprinting forward
        time.sleep(1)
        ctrl.key_up("w")
        ctrl.key_up("shift")
        
        # Mouse
        ctrl.click()
        ctrl.move_to(500, 300)
    """
    
    def __init__(self, keybinds: Optional[Dict[str, str]] = None):
        """
        Args:
            keybinds: Optional action->key mapping, e.g. {"forward": "w"}
        """
        self.keybinds = keybinds or {}
        self._pressed_keys: Dict[str, KeyState] = {}
        self._lock = threading.Lock()
        self._enabled = True
        
    @property
    def using_directinput(self) -> bool:
        """Check if using DirectInput (works with more games)"""
        return USING_DIRECTINPUT
        
    def enable(self):
        """Enable the controller"""
        self._enabled = True
        
    def disable(self):
        """Disable the controller and release all keys"""
        self._enabled = False
        self.release_all()
        
    def _resolve_key(self, key_or_action: str) -> str:
        """Resolve an action name to its bound key"""
        return self.keybinds.get(key_or_action, key_or_action)
        
    # ============ Keyboard ============
    
    def key_down(self, key: str):
        """Press and hold a key"""
        if not self._enabled:
            return
            
        key = self._resolve_key(key)
        
        with self._lock:
            if key not in self._pressed_keys or not self._pressed_keys[key].is_pressed:
                pdi.keyDown(key)
                self._pressed_keys[key] = KeyState(key, True, time.time())
                
    def key_up(self, key: str):
        """Release a held key"""
        key = self._resolve_key(key)
        
        with self._lock:
            if key in self._pressed_keys and self._pressed_keys[key].is_pressed:
                pdi.keyUp(key)
                self._pressed_keys[key].is_pressed = False
                
    def press(self, key: str, duration: float = 0.05):
        """Press and release a key"""
        if not self._enabled:
            return
            
        key = self._resolve_key(key)
        pdi.keyDown(key)
        time.sleep(duration)
        pdi.keyUp(key)
        
    def type_text(self, text: str, interval: float = 0.05):
        """Type text character by character"""
        if not self._enabled:
            return
            
        for char in text:
            pdi.press(char)
            time.sleep(interval)
            
    def release_all(self):
        """Release all held keys"""
        with self._lock:
            for key, state in self._pressed_keys.items():
                if state.is_pressed:
                    pdi.keyUp(key)
                    state.is_pressed = False
                    
    def get_pressed_keys(self) -> List[str]:
        """Get list of currently pressed keys"""
        with self._lock:
            return [k for k, v in self._pressed_keys.items() if v.is_pressed]
            
    # ============ Mouse ============
    
    def move_to(self, x: int, y: int, duration: float = 0):
        """Move mouse to absolute position"""
        if not self._enabled:
            return
            
        if duration > 0:
            pdi.moveTo(x, y, duration=duration)
        else:
            pdi.moveTo(x, y)
            
    def move_rel(self, dx: int, dy: int):
        """Move mouse relative to current position"""
        if not self._enabled:
            return
        pdi.moveRel(dx, dy)
        
    def click(self, button: str = "left", clicks: int = 1):
        """Click mouse button"""
        if not self._enabled:
            return
        pdi.click(button=button, clicks=clicks)
        
    def mouse_down(self, button: str = "left"):
        """Press and hold mouse button"""
        if not self._enabled:
            return
        pdi.mouseDown(button=button)
        
    def mouse_up(self, button: str = "left"):
        """Release mouse button"""
        pdi.mouseUp(button=button)
        
    def scroll(self, amount: int):
        """Scroll mouse wheel (positive = up, negative = down)"""
        if not self._enabled:
            return
        pdi.scroll(amount)
        
    def drag_to(self, x: int, y: int, button: str = "left", duration: float = 0.5):
        """Drag from current position to target"""
        if not self._enabled:
            return
        self.mouse_down(button)
        self.move_to(x, y, duration)
        self.mouse_up(button)
        
    # ============ Combos ============
    
    def combo(self, keys: List[str], hold_time: float = 0.1):
        """
        Execute a key combination (all pressed together).
        Example: combo(["ctrl", "c"]) for copy
        """
        if not self._enabled:
            return
            
        # Press all keys
        for key in keys:
            self.key_down(key)
            
        time.sleep(hold_time)
        
        # Release in reverse order
        for key in reversed(keys):
            self.key_up(key)
            
    def sequence(self, keys: List[str], interval: float = 0.1):
        """
        Execute keys in sequence (one after another).
        Example: sequence(["w", "w", "space"]) for double-tap forward + jump
        """
        if not self._enabled:
            return
            
        for key in keys:
            self.press(key)
            time.sleep(interval)
            
    # ============ Gaming Actions ============
    
    def look_at(self, target_x: int, target_y: int, screen_center: Tuple[int, int] = (640, 360), sensitivity: float = 0.5):
        """
        Move mouse to look at a target position.
        Calculates relative movement from screen center.
        
        Args:
            sensitivity: Scale factor for movement (0.1 - 1.0) to prevent spinning
        """
        if not self._enabled:
            return
            
        dx = int((target_x - screen_center[0]) * sensitivity)
        dy = int((target_y - screen_center[1]) * sensitivity)
        self.move_rel(dx, dy)
        
    def strafe(self, direction: str, duration: float):
        """
        Strafe in a direction while holding movement keys.
        direction: "left", "right", "forward", "back"
        """
        if not self._enabled:
            return
            
        key_map = {
            "left": "a",
            "right": "d", 
            "forward": "w",
            "back": "s"
        }
        key = self.keybinds.get(direction, key_map.get(direction, direction))
        
        self.key_down(key)
        time.sleep(duration)
        self.key_up(key)


# Quick test
if __name__ == "__main__":
    print("Game Controller Test")
    print("="*40)
    print(f"Using DirectInput: {USING_DIRECTINPUT}")
    
    ctrl = GameController()
    
    print("\nWARNING: This will simulate keypresses!")
    print("Press Ctrl+C within 3 seconds to cancel...")
    
    try:
        time.sleep(3)
        
        print("Testing key press (typing 'test')...")
        ctrl.type_text("test")
        
        print("Test complete!")
        
    except KeyboardInterrupt:
        print("\nCancelled")
    finally:
        ctrl.release_all()
