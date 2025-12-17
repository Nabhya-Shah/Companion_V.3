"""
SMART Gaming Brain - Fully Integrated LLM Decision Making
This is the proper integration that thinks like a real player

Run with: .venv-gaming\Scripts\python test_smart_brain.py
"""

import time
import sys
import os
import threading
import json
import tkinter as tk
import requests
from queue import Queue
from dataclasses import dataclass
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from companion_ai.gaming.brain import GamingBrain, GamingMode, GameState, Action
from companion_ai.gaming.memory import GameMemory


@dataclass
class GameContext:
    """Complete context for decision making"""
    goal: str = "explore"
    what_i_see: str = "nothing"
    last_actions: List[str] = None
    current_situation: str = ""
    plan: str = ""
    
    def __post_init__(self):
        if self.last_actions is None:
            self.last_actions = []


SYSTEM_PROMPT = """You are playing Minecraft. You can see through YOLO object detection and must decide actions.

IMPORTANT RULES:
1. You can only do ONE action at a time
2. Actions are: forward, back, left, right, jump, attack, look_left, look_right, wait
3. Be purposeful - don't just wander randomly
4. Remember your goal and work towards it
5. If stuck (same place for a while), try jumping or turning

Respond in this EXACT JSON format:
{"action": "forward", "thought": "I see open space ahead, moving to explore"}

ONLY these actions are valid: forward, back, left, right, jump, attack, look_left, look_right, wait"""


class SmartBrain(GamingBrain):
    """
    Fully integrated LLM brain that thinks like a real player.
    - Maintains game state and memory
    - Makes contextual decisions
    - Learns from what happens
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Ollama settings - llama3.1 is faster than qwen2.5:32b
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_model = "llama3.1:latest"
        self.ollama_timeout = 30  # Increased timeout
        
        # Game context
        self.context = GameContext()
        self.action_history: List[str] = []
        
        # LLM decision queue
        self.decision_queue = Queue()
        self.current_decision = {"action": "wait", "thought": "Starting up..."}
        
        # Threading
        self._llm_thread: Optional[threading.Thread] = None
        self._llm_running = False
        self.decision_interval = 1.5  # Seconds between LLM calls
        
    def set_goal(self, goal: str):
        """Set the AI's current goal"""
        self.context.goal = goal
        self.context.plan = ""  # Reset plan for new goal
        self._speak(f"New goal: {goal}")
        
    def start(self, game_name=None):
        """Start brain with LLM thread"""
        super().start(game_name)
        self._llm_running = True
        self._llm_thread = threading.Thread(target=self._llm_decision_loop, daemon=True)
        self._llm_thread.start()
        print("[Brain] Started with LLM decision making")
        
    def stop(self):
        """Stop everything"""
        self._llm_running = False
        super().stop()
        
    def _llm_decision_loop(self):
        """Background thread that queries LLM for decisions"""
        while self._llm_running:
            if self.mode == GamingMode.PLAYING:
                try:
                    decision = self._think()
                    if decision:
                        self.current_decision = decision
                        if self.on_speak:
                            self.on_speak(f"Thinking: {decision.get('thought', '...')}")
                except Exception as e:
                    print(f"[LLM] Error: {e}")
                    import traceback
                    traceback.print_exc()
                    
            time.sleep(self.decision_interval)
            
    def _think(self) -> dict:
        """Query LLM for next action with full context"""
        # Build context
        context = f"""GOAL: {self.context.goal}

WHAT I SEE: {self.state.objects_summary or "Nothing detected by YOLO"}

LAST 5 ACTIONS: {', '.join(self.action_history[-5:]) if self.action_history else 'None yet'}

What should I do next? Remember to respond with ONLY valid JSON like:
{{"action": "forward", "thought": "reason"}}"""

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "prompt": f"{SYSTEM_PROMPT}\n\n{context}",
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 100
                    }
                },
                timeout=self.ollama_timeout
            )
            response.raise_for_status()
            
            text = response.json().get("response", "").strip()
            print(f"[LLM Raw] {text[:200]}")
            
            # Parse JSON from response
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                decision = json.loads(json_str)
                
                # Validate action
                valid_actions = ["forward", "back", "left", "right", "jump", 
                               "attack", "look_left", "look_right", "wait"]
                action = decision.get("action", "wait").lower()
                if action not in valid_actions:
                    action = "wait"
                    
                return {
                    "action": action,
                    "thought": decision.get("thought", "")
                }
            else:
                print(f"[LLM] No JSON found in response")
                return {"action": "forward", "thought": "default exploration"}
                
        except json.JSONDecodeError as e:
            print(f"[LLM] JSON parse error: {e}")
            return {"action": "forward", "thought": "parse error, exploring"}
        except Exception as e:
            print(f"[LLM] Request error: {e}")
            return None
            
    def _decide_action(self) -> Action:
        """Use the LLM's current decision"""
        decision = self.current_decision
        action_name = decision.get("action", "wait")
        
        # Track action
        self.action_history.append(action_name)
        if len(self.action_history) > 20:
            self.action_history.pop(0)
            
        # Convert to controller action
        return self._to_controller_action(action_name, decision.get("thought", ""))
        
    def _to_controller_action(self, action_name: str, reason: str) -> Action:
        """Convert action name to controller action"""
        actions = {
            "forward": ("key_hold", {"key": "w", "duration": 0.4}),
            "back": ("key_hold", {"key": "s", "duration": 0.4}),
            "left": ("key_hold", {"key": "a", "duration": 0.4}),
            "right": ("key_hold", {"key": "d", "duration": 0.4}),
            "jump": ("key", {"key": "space"}),
            "attack": ("click", {"button": "left"}),
            "look_left": ("mouse_look", {"target": (400, 360), "sensitivity": 0.1}),
            "look_right": ("mouse_look", {"target": (880, 360), "sensitivity": 0.1}),
            "wait": ("none", {}),
        }
        
        action_type, params = actions.get(action_name, ("none", {}))
        return Action(action_type, params, reason)
        
    def _execute_action(self, action: Action):
        """Execute with key hold support"""
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


# ============ GUI ============

class SmartGamingGUI:
    def __init__(self):
        self.brain: SmartBrain = None
        self.root = tk.Tk()
        self.root.title("🧠 Smart Minecraft AI")
        self.root.geometry("450x400")
        self.root.configure(bg="#0f0f1a")
        self.root.attributes('-topmost', True)
        
        self.setup_ui()
        self.setup_brain()
        
    def setup_ui(self):
        # Title
        tk.Label(
            self.root,
            text="🧠 Smart Minecraft AI",
            font=("Segoe UI", 16, "bold"),
            fg="#a78bfa",
            bg="#0f0f1a"
        ).pack(pady=10)
        
        # Status frame
        status_frame = tk.Frame(self.root, bg="#0f0f1a")
        status_frame.pack(fill=tk.X, padx=20)
        
        self.mode_var = tk.StringVar(value="⏸ WATCHING")
        tk.Label(
            status_frame,
            textvariable=self.mode_var,
            font=("Segoe UI", 11, "bold"),
            fg="#f97316",
            bg="#0f0f1a"
        ).pack(side=tk.LEFT)
        
        # Goal
        self.goal_var = tk.StringVar(value="Goal: explore")
        tk.Label(
            self.root,
            textvariable=self.goal_var,
            font=("Segoe UI", 12),
            fg="#4ade80",
            bg="#0f0f1a"
        ).pack(pady=5)
        
        # Thought bubble
        thought_frame = tk.Frame(self.root, bg="#1a1a2e", padx=10, pady=5)
        thought_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(
            thought_frame,
            text="💭 AI Thinking:",
            font=("Segoe UI", 9),
            fg="#888",
            bg="#1a1a2e"
        ).pack(anchor=tk.W)
        
        self.thought_var = tk.StringVar(value="Waiting to start...")
        tk.Label(
            thought_frame,
            textvariable=self.thought_var,
            font=("Segoe UI", 10),
            fg="#e0e0e0",
            bg="#1a1a2e",
            wraplength=380
        ).pack(anchor=tk.W)
        
        # Command input
        input_frame = tk.Frame(self.root, bg="#0f0f1a")
        input_frame.pack(pady=10, fill=tk.X, padx=20)
        
        self.cmd_entry = tk.Entry(
            input_frame,
            font=("Segoe UI", 11),
            bg="#1a1a2e",
            fg="white",
            insertbackground="white"
        )
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cmd_entry.bind("<Return>", self.send_goal)
        
        tk.Button(
            input_frame,
            text="Set Goal",
            command=self.send_goal,
            bg="#8b5cf6",
            fg="white",
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Buttons
        btn_frame = tk.Frame(self.root, bg="#0f0f1a")
        btn_frame.pack(pady=10)
        
        buttons = [
            ("▶ Play", self.toggle_mode, "#22c55e"),
            ("Explore", lambda: self.set_goal("explore and look around"), "#3b82f6"),
            ("⏹ Stop", lambda: self.stop_immediate(), "#ef4444"),
        ]
        
        for text, cmd, color in buttons:
            tk.Button(
                btn_frame,
                text=text,
                command=cmd,
                bg=color,
                fg="white",
                font=("Segoe UI", 10, "bold"),
                width=10
            ).pack(side=tk.LEFT, padx=5)
        
        # Log
        self.log_text = tk.Text(
            self.root,
            height=6,
            font=("Consolas", 9),
            bg="#0a0a0f",
            fg="#888",
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
    def setup_brain(self):
        memory = GameMemory()
        memory.set_keybind("Minecraft", "forward", "w")
        memory.set_keybind("Minecraft", "back", "s")
        memory.set_keybind("Minecraft", "left", "a")
        memory.set_keybind("Minecraft", "right", "d")
        memory.set_keybind("Minecraft", "jump", "space")
        
        self.brain = SmartBrain(
            capture_resolution=(1280, 720),
            yolo_model="s",
            target_fps=8  # Slower for stability
        )
        
        def on_speak(msg):
            self.thought_var.set(msg)
            self.log(msg)
            
        self.brain.on_speak = on_speak
        self.brain.on_action = lambda a: None  # Quiet
        
        self.brain.start("Minecraft")
        self.log("🧠 Smart Brain initialized with llama3.1")
        self.log("Click '▶ Play' to start!")
        
    def log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
    def send_goal(self, event=None):
        goal = self.cmd_entry.get().strip()
        if goal:
            self.cmd_entry.delete(0, tk.END)
            self.set_goal(goal)
            
    def set_goal(self, goal: str):
        self.log(f"🎯 Goal → {goal}")
        self.goal_var.set(f"Goal: {goal}")
        self.root.after(2000, lambda: self.brain.set_goal(goal))
        
    def stop_immediate(self):
        self.brain.set_goal("stop and wait")
        self.brain.current_decision = {"action": "wait", "thought": "Stopping..."}
        self.log("⏹ Stopped!")
        
    def toggle_mode(self):
        if self.brain.mode == GamingMode.PLAYING:
            self.brain.set_mode(GamingMode.WATCHING)
            self.mode_var.set("⏸ WATCHING")
            self.log("Switched to WATCHING")
        else:
            self.log("Starting in 3 seconds... switch to Minecraft!")
            self.root.after(3000, self._start_playing)
            
    def _start_playing(self):
        self.brain.set_mode(GamingMode.PLAYING)
        self.mode_var.set("🎮 PLAYING")
        self.log("🎮 Now PLAYING!")
        
    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self.brain:
                self.brain.stop()


if __name__ == "__main__":
    print("Starting Smart Minecraft AI...")
    print("Using llama3.1 for intelligent decisions")
    print()
    app = SmartGamingGUI()
    app.run()
