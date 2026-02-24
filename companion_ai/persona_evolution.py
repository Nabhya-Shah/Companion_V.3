"""Compatibility wrapper for legacy persona evolution imports."""

from companion_ai.services.persona import (
    analyze_and_evolve,
    trigger_evolution_background,
    load_traits,
    save_traits,
)

__all__ = [
    "analyze_and_evolve",
    "trigger_evolution_background",
    "load_traits",
    "save_traits",
]
