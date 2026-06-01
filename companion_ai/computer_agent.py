"""Compatibility alias for legacy computer_agent import path.

This module re-exports ComputerAgent from companion_ai.runtime.computer.
"""

import sys as _sys

from companion_ai.runtime.computer import ComputerAgent, computer_agent

_sys.modules[__name__] = _computer_agent_module = _sys.modules.get("companion_ai.runtime.computer")

__all__ = ["ComputerAgent", "computer_agent"]