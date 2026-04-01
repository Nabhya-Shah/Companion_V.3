"""Main orchestration engine adapter (current production path)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple


ENGINE_NAME = "main"


def process_message(user_message: str, context: Optional[Dict] = None) -> Tuple[str, Dict]:
    """Execute message processing through the current in-process orchestrator."""
    # Resolve at call-time so tests monkeypatching companion_ai.orchestrator
    # continue to intercept this path.
    from companion_ai import orchestrator as orchestrator_module

    response, metadata = orchestrator_module.process_message(user_message, context)
    normalized = dict(metadata or {})
    normalized.setdefault("orchestration_engine", ENGINE_NAME)
    normalized.setdefault("pilot_detachable", False)
    return response, normalized
