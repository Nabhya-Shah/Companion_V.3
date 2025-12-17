"""
Game Memory Module
Stores per-game strategies, keybinds, notes, and session history
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import os


@dataclass
class GameSession:
    """Record of a gaming session"""
    start_time: str
    end_time: Optional[str] = None
    duration_minutes: float = 0
    actions_taken: int = 0
    mistakes: List[str] = field(default_factory=list)
    learnings: List[str] = field(default_factory=list)
    

@dataclass
class GameProfile:
    """Complete profile for a game"""
    name: str
    genre: str = "unknown"
    keybinds: Dict[str, str] = field(default_factory=dict)
    strategies: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    avoid_actions: List[str] = field(default_factory=list)  # Things that failed
    sessions: List[GameSession] = field(default_factory=list)
    total_play_time_minutes: float = 0
    
    
class GameMemory:
    """
    Persistent memory for gaming experiences.
    Stores strategies, keybinds, and learnings per-game.
    
    Usage:
        memory = GameMemory()
        profile = memory.get_profile("Minecraft")
        profile.strategies.append("Creepers explode - keep distance")
        memory.save_profile(profile)
    """
    
    def __init__(self, base_path: Optional[str] = None):
        if base_path:
            self.base_path = Path(base_path)
        else:
            # Default to user's home directory
            self.base_path = Path.home() / ".companion" / "games"
        self.base_path.mkdir(parents=True, exist_ok=True)
        
    def _game_dir(self, game_name: str) -> Path:
        """Get directory for a specific game"""
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in game_name)
        safe_name = safe_name.strip().replace(" ", "_").lower()
        game_dir = self.base_path / safe_name
        game_dir.mkdir(exist_ok=True)
        return game_dir
        
    def _profile_path(self, game_name: str) -> Path:
        """Get profile JSON path for a game"""
        return self._game_dir(game_name) / "profile.json"
        
    def get_profile(self, game_name: str, genre: str = "unknown") -> GameProfile:
        """Load or create a game profile"""
        path = self._profile_path(game_name)
        
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                # Convert sessions back to dataclass
                sessions = [GameSession(**s) for s in data.get('sessions', [])]
                data['sessions'] = sessions
                return GameProfile(**data)
            except (json.JSONDecodeError, TypeError):
                pass
                
        # Create new profile
        return GameProfile(name=game_name, genre=genre)
    
    def save_profile(self, profile: GameProfile):
        """Save a game profile to disk"""
        path = self._profile_path(profile.name)
        
        # Convert to dict, handling nested dataclasses
        data = asdict(profile)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
    def add_strategy(self, game_name: str, strategy: str):
        """Add a learned strategy"""
        profile = self.get_profile(game_name)
        if strategy not in profile.strategies:
            profile.strategies.append(strategy)
            self.save_profile(profile)
            
    def add_avoid_action(self, game_name: str, action: str):
        """Add an action to avoid (learned from mistakes)"""
        profile = self.get_profile(game_name)
        if action not in profile.avoid_actions:
            profile.avoid_actions.append(action)
            self.save_profile(profile)
            
    def set_keybind(self, game_name: str, action: str, key: str):
        """Set a keybind for an action"""
        profile = self.get_profile(game_name)
        profile.keybinds[action] = key
        self.save_profile(profile)
        
    def start_session(self, game_name: str) -> GameSession:
        """Start a new gaming session"""
        session = GameSession(
            start_time=datetime.now().isoformat()
        )
        return session
        
    def end_session(self, game_name: str, session: GameSession):
        """End and save a gaming session"""
        session.end_time = datetime.now().isoformat()
        
        # Calculate duration
        start = datetime.fromisoformat(session.start_time)
        end = datetime.fromisoformat(session.end_time)
        session.duration_minutes = (end - start).total_seconds() / 60
        
        profile = self.get_profile(game_name)
        profile.sessions.append(session)
        profile.total_play_time_minutes += session.duration_minutes
        self.save_profile(profile)
        
    def get_context_prompt(self, game_name: str) -> str:
        """
        Generate a context prompt for the LLM about this game.
        Include strategies, things to avoid, etc.
        """
        profile = self.get_profile(game_name)
        
        lines = [f"# Playing: {profile.name}"]
        lines.append(f"Genre: {profile.genre}")
        lines.append(f"Total play time: {profile.total_play_time_minutes:.0f} minutes")
        
        if profile.keybinds:
            lines.append("\n## Controls:")
            for action, key in profile.keybinds.items():
                lines.append(f"- {action}: {key}")
                
        if profile.strategies:
            lines.append("\n## Learned Strategies:")
            for s in profile.strategies[-10:]:  # Last 10
                lines.append(f"- {s}")
                
        if profile.avoid_actions:
            lines.append("\n## Things to Avoid:")
            for a in profile.avoid_actions[-5:]:  # Last 5
                lines.append(f"- {a}")
                
        if profile.notes:
            lines.append("\n## Notes:")
            for n in profile.notes[-5:]:
                lines.append(f"- {n}")
                
        return "\n".join(lines)
        
    def list_games(self) -> List[str]:
        """List all games with saved profiles"""
        games = []
        for item in self.base_path.iterdir():
            if item.is_dir() and (item / "profile.json").exists():
                profile = self.get_profile(item.name)
                games.append(profile.name)
        return games


# Quick test
if __name__ == "__main__":
    print("Game Memory Test")
    print("="*40)
    
    memory = GameMemory()
    
    # Create a test profile
    profile = memory.get_profile("Minecraft", genre="sandbox")
    print(f"Profile: {profile.name}")
    
    # Add some data
    memory.add_strategy("Minecraft", "Creepers explode when close - keep distance")
    memory.add_strategy("Minecraft", "Always carry a water bucket for emergencies")
    memory.set_keybind("Minecraft", "forward", "w")
    memory.set_keybind("Minecraft", "jump", "space")
    memory.set_keybind("Minecraft", "inventory", "e")
    
    # Show context
    print("\nGenerated Context:")
    print(memory.get_context_prompt("Minecraft"))
    
    print(f"\nSaved to: {memory.base_path}")
