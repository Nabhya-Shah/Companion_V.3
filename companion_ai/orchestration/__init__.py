"""Orchestration routing facade.

This package provides a detachable pilot boundary between conversation flow and
the active orchestration engine implementation.
"""

from companion_ai.orchestration.router import process_message, get_runtime_descriptor

__all__ = ["process_message", "get_runtime_descriptor"]
