"""
Game Detection Module
Monitors running processes to detect when games are launched
"""

import psutil
import time
import json
from pathlib import Path
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
import threading


@dataclass
class GameInfo:
    """Information about a detected game"""
    name: str
    exe_name: str
    process_id: int
    genre: str = "unknown"
    
    
# Known games database - will be expanded
KNOWN_GAMES = {
    # Minecraft variants
    "javaw.exe": {"name": "Minecraft Java", "genre": "sandbox"},
    "minecraft.exe": {"name": "Minecraft", "genre": "sandbox"},
    "minecraftlauncher.exe": {"name": "Minecraft Launcher", "genre": "launcher"},
    
    # Roblox
    "robloxplayerbeta.exe": {"name": "Roblox", "genre": "platform"},
    "robloxstudiobeta.exe": {"name": "Roblox Studio", "genre": "development"},
    
    # Path of Exile
    "pathofexile.exe": {"name": "Path of Exile", "genre": "arpg"},
    "pathofexile_x64.exe": {"name": "Path of Exile", "genre": "arpg"},
    
    # Popular games
    "eldenring.exe": {"name": "Elden Ring", "genre": "action_rpg"},
    "witcher3.exe": {"name": "The Witcher 3", "genre": "rpg"},
    "cyberpunk2077.exe": {"name": "Cyberpunk 2077", "genre": "rpg"},
    "gta5.exe": {"name": "Grand Theft Auto V", "genre": "action"},
    "rocketleague.exe": {"name": "Rocket League", "genre": "sports"},
    "valorant.exe": {"name": "Valorant", "genre": "fps"},
    "csgo.exe": {"name": "CS:GO", "genre": "fps"},
    "cs2.exe": {"name": "Counter-Strike 2", "genre": "fps"},
    "fortnite.exe": {"name": "Fortnite", "genre": "battle_royale"},
    "apex_legends.exe": {"name": "Apex Legends", "genre": "battle_royale"},
    "overwatch.exe": {"name": "Overwatch 2", "genre": "fps"},
    "leagueoflegends.exe": {"name": "League of Legends", "genre": "moba"},
    "dota2.exe": {"name": "Dota 2", "genre": "moba"},
    "terraria.exe": {"name": "Terraria", "genre": "sandbox"},
    "stardewvalley.exe": {"name": "Stardew Valley", "genre": "simulation"},
    "hollowknight.exe": {"name": "Hollow Knight", "genre": "metroidvania"},
    "celeste.exe": {"name": "Celeste", "genre": "platformer"},
    "hades.exe": {"name": "Hades", "genre": "roguelike"},
    "baldursgate3.exe": {"name": "Baldur's Gate 3", "genre": "rpg"},
    "bg3.exe": {"name": "Baldur's Gate 3", "genre": "rpg"},
}


class GameDetector:
    """
    Monitors system processes to detect running games.
    
    Usage:
        detector = GameDetector()
        detector.on_game_start = lambda game: print(f"Started: {game.name}")
        detector.on_game_end = lambda game: print(f"Ended: {game.name}")
        detector.start()
    """
    
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self.known_games = KNOWN_GAMES.copy()
        self.current_game: Optional[GameInfo] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.on_game_start: Optional[Callable[[GameInfo], None]] = None
        self.on_game_end: Optional[Callable[[GameInfo], None]] = None
        
    def add_game(self, exe_name: str, name: str, genre: str = "unknown"):
        """Add a custom game to the detection list"""
        self.known_games[exe_name.lower()] = {"name": name, "genre": genre}
        
    def get_running_games(self) -> List[GameInfo]:
        """Get list of currently running known games"""
        games = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                exe = proc.info['name'].lower()
                if exe in self.known_games:
                    info = self.known_games[exe]
                    games.append(GameInfo(
                        name=info["name"],
                        exe_name=exe,
                        process_id=proc.info['pid'],
                        genre=info.get("genre", "unknown")
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return games
    
    def detect_once(self) -> Optional[GameInfo]:
        """Single detection check, returns first found game"""
        games = self.get_running_games()
        return games[0] if games else None
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self._running:
            detected = self.detect_once()
            
            if detected and not self.current_game:
                # Game started
                self.current_game = detected
                if self.on_game_start:
                    self.on_game_start(detected)
                    
            elif not detected and self.current_game:
                # Game ended
                ended_game = self.current_game
                self.current_game = None
                if self.on_game_end:
                    self.on_game_end(ended_game)
                    
            elif detected and self.current_game:
                # Check if different game
                if detected.exe_name != self.current_game.exe_name:
                    # Switched games
                    if self.on_game_end:
                        self.on_game_end(self.current_game)
                    self.current_game = detected
                    if self.on_game_start:
                        self.on_game_start(detected)
            
            time.sleep(self.poll_interval)
    
    def start(self):
        """Start background monitoring"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop background monitoring"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.poll_interval * 2)
            self._thread = None
            
    def is_game_running(self) -> bool:
        """Check if any known game is currently running"""
        return self.current_game is not None


# Quick test
if __name__ == "__main__":
    print("Game Detector Test")
    print("="*40)
    
    detector = GameDetector()
    
    # Check for running games
    games = detector.get_running_games()
    if games:
        print(f"Found {len(games)} game(s) running:")
        for game in games:
            print(f"  - {game.name} ({game.exe_name}) [PID: {game.process_id}]")
    else:
        print("No known games currently running")
        
    print("\nKnown games:", len(detector.known_games))
