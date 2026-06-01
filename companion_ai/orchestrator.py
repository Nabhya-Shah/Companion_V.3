"""Compatibility alias for legacy orchestrator import path.

All symbols are re-exported from companion_ai.runtime.orchestrator for backward compatibility.
"""

import sys as _sys

from companion_ai.runtime.orchestrator import (
    Orchestrator,
    OrchestratorDecision,
    OrchestratorAction,
    process_message,
    get_orchestrator,
)

__all__ = [
    "Orchestrator",
    "OrchestratorDecision",
    "OrchestratorAction",
    "process_message",
    "get_orchestrator",
]