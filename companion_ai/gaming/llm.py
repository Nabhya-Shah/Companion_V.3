"""
Gaming LLM - Intelligent decision making for games
Uses LLM to interpret vision data and decide actions
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Try to import OpenAI-compatible client
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@dataclass
class LLMDecision:
    """Decision from the LLM"""
    action: str  # "move_forward", "look_at", "attack", "wait", "speak", etc.
    params: Dict[str, Any]
    reasoning: str
    confidence: float = 1.0


GAMING_SYSTEM_PROMPT = """You are an AI gaming agent controlling a character in a video game.

Your job is to:
1. Understand the current game state from YOLO object detections
2. Follow the user's goal/command
3. Decide what action to take RIGHT NOW (one action at a time)

Available actions:
- move_forward: Walk forward {"duration": seconds}
- move_back: Walk backward {"duration": seconds}
- strafe_left: Strafe left {"duration": seconds}
- strafe_right: Strafe right {"duration": seconds}
- jump: Jump {}
- look_at: Look at coordinates {"x": int, "y": int}
- attack: Left click to attack {}
- use: Right click to use/place {}
- wait: Do nothing for a moment {}
- speak: Say something {"text": "message"}

Respond with JSON only:
{
    "action": "action_name",
    "params": {},
    "reasoning": "Brief explanation",
    "confidence": 0.0-1.0
}

Be decisive and take action! Don't overthink. If unsure, explore by moving around.
"""


class GamingLLM:
    """
    LLM-powered decision making for games.
    
    Connects to any OpenAI-compatible API (local or cloud).
    """
    
    def __init__(
        self,
        api_base: str = "http://localhost:1234/v1",  # LM Studio default
        api_key: str = "not-needed",
        model: str = "local-model"
    ):
        if not HAS_OPENAI:
            raise ImportError("openai package required: pip install openai")
            
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key
        )
        self.model = model
        self.system_prompt = GAMING_SYSTEM_PROMPT
        self.current_goal: str = "Explore and look around"
        self.game_context: str = ""
        
    def set_goal(self, goal: str):
        """Set the current goal/command"""
        self.current_goal = goal
        
    def set_game_context(self, context: str):
        """Set game-specific context (from memory)"""
        self.game_context = context
        
    def decide(
        self,
        detections_summary: str,
        recent_actions: List[str] = None
    ) -> Optional[LLMDecision]:
        """
        Get a decision from the LLM based on current state.
        
        Args:
            detections_summary: Text summary of YOLO detections
            recent_actions: List of recent actions taken
            
        Returns:
            LLMDecision or None if failed
        """
        # Build the user message
        parts = [f"Current goal: {self.current_goal}"]
        
        if self.game_context:
            parts.append(f"\nGame info:\n{self.game_context}")
            
        parts.append(f"\nWhat I see: {detections_summary or 'Nothing detected'}")
        
        if recent_actions:
            parts.append(f"\nRecent actions: {', '.join(recent_actions[-5:])}")
            
        parts.append("\nWhat should I do RIGHT NOW? Respond with JSON only.")
        
        user_message = "\n".join(parts)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            # Handle case where LLM wraps in markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            data = json.loads(content)
            
            return LLMDecision(
                action=data.get("action", "wait"),
                params=data.get("params", {}),
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 1.0)
            )
            
        except json.JSONDecodeError as e:
            print(f"[LLM] Failed to parse JSON: {e}")
            print(f"[LLM] Raw response: {content[:200]}")
            return None
        except Exception as e:
            print(f"[LLM] Error: {e}")
            return None


class SimpleLLM:
    """
    Simple rule-based "LLM" for testing without actual LLM.
    Parses basic commands and translates to actions.
    """
    
    def __init__(self):
        self.current_goal = "Explore"
        self.game_context = ""
        
    def set_goal(self, goal: str):
        self.current_goal = goal.lower()
        
    def set_game_context(self, context: str):
        self.game_context = context
        
    def decide(
        self,
        detections_summary: str,
        recent_actions: List[str] = None
    ) -> LLMDecision:
        """Simple rule-based decisions"""
        goal = self.current_goal
        
        # Parse simple commands
        if "forward" in goal or "go" in goal:
            return LLMDecision("move_forward", {"duration": 0.5}, "Moving forward")
            
        elif "back" in goal:
            return LLMDecision("move_back", {"duration": 0.5}, "Moving backward")
            
        elif "left" in goal:
            return LLMDecision("strafe_left", {"duration": 0.5}, "Strafing left")
            
        elif "right" in goal:
            return LLMDecision("strafe_right", {"duration": 0.5}, "Strafing right")
            
        elif "jump" in goal:
            return LLMDecision("jump", {}, "Jumping")
            
        elif "look" in goal:
            # Look around HORIZONTALLY ONLY - never change Y to prevent camera drift!
            import random
            x = random.randint(400, 880)  # Left-right only
            y = 360  # ALWAYS center - no vertical movement!
            return LLMDecision("look_at", {"x": x, "y": y}, "Looking left/right")
            
        elif "attack" in goal or "hit" in goal:
            return LLMDecision("attack", {}, "Attacking")
            
        elif "stop" in goal or "wait" in goal:
            return LLMDecision("wait", {}, "Waiting")
            
        elif "spin" in goal:
            return LLMDecision("look_at", {"x": 1000, "y": 360}, "Spinning")
            
        elif "swim" in goal or "up" in goal:
            return LLMDecision("jump", {}, "Swimming up / jumping")
            
        # Default: explore (move + occasional jump to unstick)
        import random
        roll = random.random()
        if roll < 0.15:
            # Occasional jump to escape water/obstacles
            return LLMDecision("jump", {}, "Exploring - jumping to unstick")
        elif roll < 0.3:
            # Look around HORIZONTALLY ONLY
            x = random.randint(400, 880)
            y = 360  # ALWAYS center - prevents camera drifting down!
            return LLMDecision("look_at", {"x": x, "y": y}, "Exploring - looking left/right")
        else:
            return LLMDecision("move_forward", {"duration": 0.3}, "Exploring - moving")


# Test
if __name__ == "__main__":
    print("Testing SimpleLLM...")
    
    llm = SimpleLLM()
    
    llm.set_goal("go forward")
    decision = llm.decide("Some objects ahead")
    print(f"Goal: 'go forward' -> {decision.action} ({decision.reasoning})")
    
    llm.set_goal("look around")
    decision = llm.decide("")
    print(f"Goal: 'look around' -> {decision.action} ({decision.reasoning})")
    
    llm.set_goal("explore")
    decision = llm.decide("")
    print(f"Goal: 'explore' -> {decision.action} ({decision.reasoning})")
