"""
Gaming Brain - Decision Engine
Connects vision (YOLO + VLM) with controller for gameplay
"""

import time
import threading
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import queue

from .vision.capture import ScreenCapture
from .vision.yolo import YOLODetector, Detection
from .controller import GameController
from .memory import GameMemory, GameSession
from .detector import GameDetector, GameInfo


class GamingMode(Enum):
    """Current gaming mode"""
    WATCHING = "watching"      # AI observes, doesn't control
    PLAYING = "playing"        # AI has full control
    ASSISTING = "assisting"    # AI gives tips, doesn't control


@dataclass
class GameState:
    """Current state of the game"""
    detections: List[Detection] = field(default_factory=list)
    frame_time: float = 0
    objects_summary: str = ""
    vlm_context: str = ""  # From slow VLM, updated every few seconds
    

@dataclass
class Action:
    """An action to take"""
    action_type: str  # "key", "mouse", "speak", "none"
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    confidence: float = 1.0


class GamingBrain:
    """
    The decision-making engine for gaming.
    
    Combines fast YOLO detection with game memory and controller
    to make real-time decisions.
    
    Usage:
        brain = GamingBrain()
        brain.on_speak = lambda text: print(f"AI says: {text}")
        brain.start("Minecraft")
        
        # Later...
        brain.set_mode(GamingMode.PLAYING)  # AI takes control
        
        # To stop
        brain.stop()
    """
    
    def __init__(
        self,
        capture_resolution: tuple = (1280, 720),
        yolo_model: str = "s",  # n=nano, s=small
        target_fps: int = 30
    ):
        # Components
        self.capture = ScreenCapture(resolution=capture_resolution)
        self.yolo = YOLODetector(model_size=yolo_model)
        self.controller = GameController()
        self.memory = GameMemory()
        self.detector = GameDetector()
        
        # State
        self.mode = GamingMode.WATCHING
        self.current_game: Optional[GameInfo] = None
        self.current_session: Optional[GameSession] = None
        self.state = GameState()
        self.target_fps = target_fps
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.on_speak: Optional[Callable[[str], None]] = None
        self.on_state_update: Optional[Callable[[GameState], None]] = None
        self.on_action: Optional[Callable[[Action], None]] = None
        
        # Action queue for async execution
        self._action_queue: queue.Queue = queue.Queue()
        
        # Safety
        self._last_action_time = 0
        self._action_cooldown = 0.1  # Min time between actions
        
    def set_mode(self, mode: GamingMode):
        """Change the gaming mode"""
        old_mode = self.mode
        self.mode = mode
        
        if mode == GamingMode.PLAYING:
            self.controller.enable()
            self._speak("Taking control!")
        elif old_mode == GamingMode.PLAYING:
            self.controller.disable()
            self._speak("Handing control back to you!")
            
    def _speak(self, text: str):
        """Queue speech output"""
        if self.on_speak:
            self.on_speak(text)
            
    def start(self, game_name: Optional[str] = None):
        """Start the gaming brain"""
        if self._running:
            return
            
        # Detect or set game
        if game_name:
            profile = self.memory.get_profile(game_name)
            self.current_game = GameInfo(
                name=game_name,
                exe_name="",
                process_id=0,
                genre=profile.genre
            )
        else:
            self.current_game = self.detector.detect_once()
            
        if self.current_game:
            self.current_session = self.memory.start_session(self.current_game.name)
            self._speak(f"Ready to play {self.current_game.name}!")
            
            # Load keybinds
            profile = self.memory.get_profile(self.current_game.name)
            self.controller.keybinds = profile.keybinds
            
        self._running = True
        self._thread = threading.Thread(target=self._game_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop the gaming brain"""
        self._running = False
        self.controller.disable()
        self.controller.release_all()
        
        # Save session
        if self.current_game and self.current_session:
            self.memory.end_session(self.current_game.name, self.current_session)
            
        if self._thread:
            self._thread.join(timeout=2)
            
    def _game_loop(self):
        """Main game loop - runs at target FPS"""
        frame_time = 1.0 / self.target_fps
        
        while self._running:
            loop_start = time.perf_counter()
            
            try:
                # 1. Capture frame
                frame = self.capture.grab_numpy()
                
                # 2. Run YOLO detection
                detections = self.yolo.detect(frame)
                
                # 3. Update state
                self.state.detections = detections
                self.state.frame_time = time.time()
                self.state.objects_summary = self.yolo.summarize(detections)
                
                # 4. Decide action (if playing)
                if self.mode == GamingMode.PLAYING:
                    action = self._decide_action()
                    if action and action.action_type != "none":
                        self._execute_action(action)
                        
                # 5. Notify listeners
                if self.on_state_update:
                    self.on_state_update(self.state)
                    
            except Exception as e:
                print(f"[Brain] Error in game loop: {e}")
                
            # Maintain target FPS
            elapsed = time.perf_counter() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    def _decide_action(self) -> Optional[Action]:
        """
        Decide what action to take based on current state.
        This is the core decision logic.
        """
        detections = self.state.detections
        
        if not detections:
            # Nothing detected - maybe explore?
            return Action("none", reason="No objects detected")
            
        # Example: Simple logic for Minecraft
        # In a real implementation, this would use the LLM
        
        # Check for enemies (persons in COCO = could be mobs)
        enemies = self.yolo.find_class(detections, "person")
        if enemies:
            # Found something! Look at it
            nearest = self.yolo.find_nearest(enemies, (640, 360))
            if nearest:
                return Action(
                    "mouse_look",
                    params={"target": nearest.center},
                    reason=f"Looking at {nearest.class_name}"
                )
                
        return Action("none")
        
    def _execute_action(self, action: Action):
        """Execute an action through the controller"""
        # Cooldown check
        now = time.time()
        if now - self._last_action_time < self._action_cooldown:
            return
        self._last_action_time = now
        
        # Track action
        if self.current_session:
            self.current_session.actions_taken += 1
            
        # Notify
        if self.on_action:
            self.on_action(action)
            
        # Execute
        if action.action_type == "key":
            key = action.params.get("key", "")
            hold = action.params.get("hold", False)
            if hold:
                self.controller.key_down(key)
            else:
                self.controller.press(key)
                
        elif action.action_type == "key_up":
            self.controller.key_up(action.params.get("key", ""))
            
        elif action.action_type == "mouse_look":
            target = action.params.get("target", (640, 360))
            sensitivity = action.params.get("sensitivity", 0.5)
            self.controller.look_at(target[0], target[1], sensitivity=sensitivity)
            
        elif action.action_type == "click":
            button = action.params.get("button", "left")
            self.controller.click(button)
            
        elif action.action_type == "speak":
            self._speak(action.params.get("text", ""))
            
    def add_learning(self, learning: str):
        """Add a learning/strategy from gameplay"""
        if self.current_game:
            self.memory.add_strategy(self.current_game.name, learning)
            
    def add_mistake(self, mistake: str):
        """Record a mistake to avoid"""
        if self.current_game:
            self.memory.add_avoid_action(self.current_game.name, mistake)
            if self.current_session:
                self.current_session.mistakes.append(mistake)


# Simple demo
if __name__ == "__main__":
    print("Gaming Brain Demo")
    print("="*40)
    print("This demo will:")
    print("1. Start capturing screen")
    print("2. Run YOLO detection")
    print("3. Print what it sees")
    print("\nPress Ctrl+C to stop\n")
    
    brain = GamingBrain(target_fps=10)  # Lower FPS for demo
    
    def on_state(state: GameState):
        if state.detections:
            print(f"[{time.strftime('%H:%M:%S')}] {state.objects_summary}")
            
    brain.on_state_update = on_state
    brain.on_speak = lambda t: print(f"[SPEAK] {t}")
    
    try:
        brain.start("Demo Game")
        print("Brain started! Watching screen...\n")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
        brain.stop()
        print("Done!")
