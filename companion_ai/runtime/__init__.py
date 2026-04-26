"""Runtime subsystem package.

Canonical runtime modules:
1. companion_ai.runtime.conversation
2. companion_ai.runtime.computer
3. companion_ai.runtime.orchestrator
"""

from companion_ai.runtime.conversation import ConversationSession
from companion_ai.runtime.computer import ComputerAgent, computer_agent
from companion_ai.runtime.orchestrator import (
    Orchestrator,
    OrchestratorAction,
    OrchestratorDecision,
    get_orchestrator,
    process_message,
    process_message_async,
)

__all__ = [
    "ConversationSession",
    "ComputerAgent",
    "computer_agent",
    "Orchestrator",
    "OrchestratorAction",
    "OrchestratorDecision",
    "get_orchestrator",
    "process_message",
    "process_message_async",
]
