# companion_ai/local_loops/__init__.py
"""
Local Loops Module - Specialized local model executors.

Each loop is a self-contained unit that can have multiple models working together.
Loops are called by the 120B orchestrator and return structured results.
"""

from .base import Loop, LoopResult, LoopStatus
from .registry import get_loop, list_loops, register_loop, get_capabilities_summary

__all__ = [
    'Loop',
    'LoopResult',
    'LoopStatus',
    'get_loop',
    'list_loops',
    'register_loop',
    'get_capabilities_summary',
]
