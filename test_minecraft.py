"""
Minecraft Test Script with Command Terminal
Tests the gaming agent with Minecraft - send commands via terminal

Run with: .venv-gaming\Scripts\python test_minecraft.py
"""

import time
import sys
import os
import threading
from queue import Queue

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from companion_ai.gaming.brain import GamingBrain, GamingMode, GameState, Action
from companion_ai.gaming.memory import GameMemory
from companion_ai.gaming.llm import SimpleLLM, LLMDecision


class SmartGamingBrain(GamingBrain):
    """Extended brain with LLM decision making"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = SimpleLLM()  # Use simple LLM for now
        self.recent_actions: list = []
        
    def set_goal(self, goal: str):
        """Set the AI's current goal"""
        self.llm.set_goal(goal)
        self._speak(f"New goal: {goal}")
        
    def _decide_action(self) -> Action:
        """Use LLM to decide action"""
        # Get LLM decision
        decision = self.llm.decide(
            self.state.objects_summary,
            self.recent_actions
        )
        
        if not decision:
            return Action("none")
            
        # Track action
        self.recent_actions.append(decision.action)
        if len(self.recent_actions) > 10:
            self.recent_actions.pop(0)
            
        # Convert LLM decision to Action
        return self._llm_to_action(decision)
        
    def _llm_to_action(self, decision: LLMDecision) -> Action:
        """Convert LLM decision to controller action"""
        action = decision.action
        params = decision.params
        
        if action == "move_forward":
            return Action("key_hold", {
                "key": "w",
                "duration": params.get("duration", 0.3)
            }, decision.reasoning)
            
        elif action == "move_back":
            return Action("key_hold", {
                "key": "s",
                "duration": params.get("duration", 0.3)
            }, decision.reasoning)
            
        elif action == "strafe_left":
            return Action("key_hold", {
                "key": "a",
                "duration": params.get("duration", 0.3)
            }, decision.reasoning)
            
        elif action == "strafe_right":
            return Action("key_hold", {
                "key": "d",
                "duration": params.get("duration", 0.3)
            }, decision.reasoning)
            
        elif action == "jump":
            return Action("key", {"key": "space"}, decision.reasoning)
            
        elif action == "look_at":
            return Action("mouse_look", {
                "target": (params.get("x", 640), params.get("y", 360)),
                "sensitivity": 0.3  # Reduced sensitivity for smoother movement
            }, decision.reasoning)
            
        elif action == "attack":
            return Action("click", {"button": "left"}, decision.reasoning)
            
        elif action == "use":
            return Action("click", {"button": "right"}, decision.reasoning)
            
        elif action == "speak":
            return Action("speak", {"text": params.get("text", "")}, decision.reasoning)
            
        return Action("none", reason=decision.reasoning)
        
    def _execute_action(self, action: Action):
        """Extended action execution"""
        if action.action_type == "key_hold":
            key = action.params.get("key", "w")
            duration = action.params.get("duration", 0.3)
            self.controller.key_down(key)
            time.sleep(duration)
            self.controller.key_up(key)
            
            if self.current_session:
                self.current_session.actions_taken += 1
        else:
            super()._execute_action(action)


def print_header():
    """Print the header"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("  MINECRAFT GAMING AGENT - Command Terminal")
    print("="*60)
    print()


def print_help():
    """Print help"""
    print("\nCommands:")
    print("  go forward    - Move forward")
    print("  go back       - Move backward")
    print("  go left/right - Strafe")
    print("  look around   - Look around randomly")
    print("  jump          - Jump")
    print("  attack        - Attack")
    print("  explore       - Explore randomly")
    print("  stop          - Stop moving")
    print()
    print("  play          - Switch to PLAYING mode")
    print("  watch         - Switch to WATCHING mode")
    print("  quit          - Exit")
    print()


def main():
    print_header()
    
    print("Instructions:")
    print("1. Open Minecraft and start a Creative world")
    print("2. Press ENTER when Minecraft is ready")
    print("3. Type commands to control the AI")
    print()
    
    input("Press ENTER when ready...")
    
    print("\nInitializing...")
    
    # Set up keybinds
    memory = GameMemory()
    memory.set_keybind("Minecraft", "forward", "w")
    memory.set_keybind("Minecraft", "back", "s")
    memory.set_keybind("Minecraft", "left", "a")
    memory.set_keybind("Minecraft", "right", "d")
    memory.set_keybind("Minecraft", "jump", "space")
    
    # Create smart brain
    brain = SmartGamingBrain(
        capture_resolution=(1280, 720),
        yolo_model="s",
        target_fps=10  # 10 FPS for testing
    )
    
    # Status display
    last_state = {"detections": "", "mode": "WATCHING", "goal": "explore"}
    
    def on_state(state: GameState):
        if state.objects_summary != last_state["detections"]:
            last_state["detections"] = state.objects_summary
            
    def on_action(action: Action):
        if action.action_type != "none":
            print(f"  [ACTION] {action.action_type}: {action.reason}")
            
    def on_speak(text: str):
        print(f"  [AI] {text}")
        
    brain.on_state_update = on_state
    brain.on_action = on_action
    brain.on_speak = on_speak
    
    # Start brain
    brain.start("Minecraft")
    
    print_header()
    print("AI is running in WATCHING mode.")
    print("Type 'play' to let AI take control, 'help' for commands.\n")
    
    # Status thread
    def status_printer():
        while brain._running:
            # Print status line
            mode = brain.mode.value.upper()
            detections = last_state["detections"] or "Nothing"
            goal = brain.llm.current_goal
            
            # Only print if we have detections
            if brain.mode == GamingMode.PLAYING:
                sys.stdout.write(f"\r[{mode}] Goal: {goal[:30]} | Sees: {detections[:40]}    ")
                sys.stdout.flush()
            time.sleep(1)
            
    status_thread = threading.Thread(target=status_printer, daemon=True)
    status_thread.start()
    
    # Main command loop
    try:
        while True:
            try:
                cmd = input("\n> ").strip().lower()
            except EOFError:
                break
                
            if not cmd:
                continue
                
            if cmd == "quit" or cmd == "exit" or cmd == "q":
                break
                
            elif cmd == "help" or cmd == "?":
                print_help()
                
            elif cmd == "play":
                print("\n>> Switching to PLAYING mode in 3 seconds...")
                print(">> Focus the Minecraft window now!")
                time.sleep(3)
                brain.set_mode(GamingMode.PLAYING)
                print(">> AI is now PLAYING!")
                
            elif cmd == "watch":
                brain.set_mode(GamingMode.WATCHING)
                print(">> Switched to WATCHING mode")
                
            elif cmd == "status":
                mode = brain.mode.value.upper()
                goal = brain.llm.current_goal
                detections = last_state["detections"] or "Nothing"
                print(f"\nMode: {mode}")
                print(f"Goal: {goal}")
                print(f"Sees: {detections}")
                
            else:
                # Treat as a goal command
                brain.set_goal(cmd)
                print(f">> Goal set: {cmd}")
                
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
        
    finally:
        print("\nStopping...")
        brain.stop()
        print("Done!")


if __name__ == "__main__":
    main()
