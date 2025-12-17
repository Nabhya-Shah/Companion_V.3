"""
Gaming Module for Companion AI
Enables AI to detect, watch, and play games
"""

from .detector import GameDetector
from .memory import GameMemory
from .brain import GamingBrain, GamingMode
from .controller import GameController

__all__ = ['GameDetector', 'GameMemory', 'GamingBrain', 'GamingMode', 'GameController']
