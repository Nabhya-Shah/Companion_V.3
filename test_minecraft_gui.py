"""
Minecraft Gaming Agent - GUI Version
Simple window for sending commands to the AI

Run with: .venv-gaming\Scripts\python test_minecraft_gui.py
"""

import time
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from companion_ai.gaming.brain import GamingBrain, GamingMode, GameState, Action
from companion_ai.gaming.memory import GameMemory
from companion_ai.gaming.llm import SimpleLLM, LLMDecision


class SmartGamingBrain(GamingBrain):
    """Extended brain with LLM decision making"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = SimpleLLM()
        self.recent_actions: list = []
        
    def set_goal(self, goal: str):
        """Set the AI's current goal"""
        self.llm.set_goal(goal)
        self._speak(f"New goal: {goal}")
        
    def _decide_action(self) -> Action:
        """Use LLM to decide action - ignore YOLO for now"""
        # Get LLM decision based on goal, NOT YOLO detections
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
                "sensitivity": 0.2  # Even lower sensitivity
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


class GamingGUI:
    """Simple GUI for controlling the gaming agent"""
    
    def __init__(self):
        self.brain: SmartGamingBrain = None
        self.root = tk.Tk()
        self.root.title("Minecraft Gaming Agent")
        self.root.geometry("400x300")
        self.root.configure(bg="#1a1a2e")
        
        # Make window stay on top
        self.root.attributes('-topmost', True)
        
        self.setup_ui()
        self.setup_brain()
        
    def setup_ui(self):
        """Create the UI"""
        style = ttk.Style()
        style.configure("TButton", padding=5)
        style.configure("TEntry", padding=5)
        
        # Title
        title = tk.Label(
            self.root, 
            text="🎮 Minecraft AI Controller",
            font=("Segoe UI", 14, "bold"),
            fg="#8b5cf6",
            bg="#1a1a2e"
        )
        title.pack(pady=10)
        
        # Status
        self.status_var = tk.StringVar(value="Mode: WATCHING")
        status = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            fg="#888",
            bg="#1a1a2e"
        )
        status.pack()
        
        # Goal display
        self.goal_var = tk.StringVar(value="Goal: explore")
        goal_label = tk.Label(
            self.root,
            textvariable=self.goal_var,
            font=("Segoe UI", 10),
            fg="#4ade80",
            bg="#1a1a2e"
        )
        goal_label.pack(pady=5)
        
        # Command input
        input_frame = tk.Frame(self.root, bg="#1a1a2e")
        input_frame.pack(pady=10, fill=tk.X, padx=20)
        
        self.command_entry = tk.Entry(
            input_frame,
            font=("Segoe UI", 12),
            bg="#2a2a3e",
            fg="white",
            insertbackground="white"
        )
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.command_entry.bind("<Return>", self.send_command)
        
        send_btn = tk.Button(
            input_frame,
            text="Send",
            command=self.send_command,
            bg="#8b5cf6",
            fg="white",
            font=("Segoe UI", 10, "bold")
        )
        send_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Quick buttons
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(pady=10)
        
        buttons = [
            ("▶ Play", lambda: self.toggle_mode()),
            ("Explore", lambda: self.set_goal("explore")),
            ("Jump", lambda: self.set_goal_immediate("jump")),
            ("Stop", lambda: self.set_goal_immediate("stop")),
        ]
        
        for text, cmd in buttons:
            btn = tk.Button(
                btn_frame,
                text=text,
                command=cmd,
                bg="#2a2a3e",
                fg="white",
                font=("Segoe UI", 9)
            )
            btn.pack(side=tk.LEFT, padx=3)
            
        # Log
        self.log_text = tk.Text(
            self.root,
            height=5,
            font=("Consolas", 9),
            bg="#0a0a0f",
            fg="#888",
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
    def setup_brain(self):
        """Initialize the gaming brain"""
        # Set up Minecraft keybinds
        memory = GameMemory()
        memory.set_keybind("Minecraft", "forward", "w")
        memory.set_keybind("Minecraft", "back", "s")
        memory.set_keybind("Minecraft", "left", "a")
        memory.set_keybind("Minecraft", "right", "d")
        memory.set_keybind("Minecraft", "jump", "space")
        
        self.brain = SmartGamingBrain(
            capture_resolution=(1280, 720),
            yolo_model="s",
            target_fps=10
        )
        
        self.brain.on_speak = self.log
        self.brain.on_action = lambda a: self.log(f"[{a.action_type}] {a.reason}")
        
        # Start brain
        self.brain.start("Minecraft")
        self.log("Brain started in WATCHING mode")
        self.log("Click 'Play' or type a command")
        
    def log(self, message: str):
        """Add message to log"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
    def send_command(self, event=None):
        """Send command from entry"""
        cmd = self.command_entry.get().strip()
        if not cmd:
            return
            
        self.command_entry.delete(0, tk.END)
        
        if cmd.lower() == "play":
            self.toggle_mode()
        elif cmd.lower() == "watch":
            self.brain.set_mode(GamingMode.WATCHING)
            self.status_var.set("Mode: WATCHING")
        else:
            self.set_goal(cmd)
            
    def set_goal(self, goal: str):
        """Set a new goal with delay for window switching"""
        self.log(f"Goal → {goal} (3 sec delay...)")
        self.goal_var.set(f"Goal: {goal} (switching...)")
        # 3 second delay so user can switch to Minecraft
        self.root.after(3000, lambda: self._apply_goal(goal))
        
    def set_goal_immediate(self, goal: str):
        """Set goal immediately with no delay (for stop, jump, etc.)"""
        self.brain.set_goal(goal)
        self.goal_var.set(f"Goal: {goal}")
        self.log(f"Goal: {goal} (immediate)")
        
    def _apply_goal(self, goal: str):
        """Actually apply the goal after delay"""
        self.brain.set_goal(goal)
        self.goal_var.set(f"Goal: {goal}")
        self.log(f"Goal active: {goal}")
        
    def toggle_mode(self):
        """Toggle between WATCHING and PLAYING"""
        if self.brain.mode == GamingMode.PLAYING:
            self.brain.set_mode(GamingMode.WATCHING)
            self.status_var.set("Mode: WATCHING")
            self.log("Switched to WATCHING")
        else:
            self.log("Switching to PLAYING in 3 seconds...")
            self.log("Focus Minecraft window now!")
            self.root.after(3000, self._start_playing)
            
    def _start_playing(self):
        """Start playing mode after delay"""
        self.brain.set_mode(GamingMode.PLAYING)
        self.status_var.set("Mode: PLAYING")
        self.log("Now PLAYING!")
        
    def run(self):
        """Run the GUI"""
        try:
            self.root.mainloop()
        finally:
            if self.brain:
                self.brain.stop()


def main():
    print("Starting Minecraft Gaming Agent GUI...")
    print("A window will appear - keep it on your second monitor!")
    print()
    
    app = GamingGUI()
    app.run()


if __name__ == "__main__":
    main()
