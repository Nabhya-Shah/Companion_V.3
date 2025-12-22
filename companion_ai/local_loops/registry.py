# companion_ai/local_loops/registry.py
"""
Loop Registry - Discover and manage available loops.

Loops auto-register when imported. The orchestrator uses this
to find and invoke the right loop for each task.
"""

import logging
from typing import Dict, Optional, Type, List
from .base import Loop

logger = logging.getLogger(__name__)

# Global registry of available loops
_LOOP_REGISTRY: Dict[str, Type[Loop]] = {}

# Singleton instances (created on first use)
_LOOP_INSTANCES: Dict[str, Loop] = {}


def register_loop(loop_class: Type[Loop]) -> Type[Loop]:
    """Decorator to register a loop class.
    
    Usage:
        @register_loop
        class MyLoop(Loop):
            name = "my_loop"
            ...
    """
    name = loop_class.name
    if name in _LOOP_REGISTRY:
        logger.warning(f"Loop '{name}' already registered, overwriting")
    _LOOP_REGISTRY[name] = loop_class
    logger.info(f"Registered loop: {name}")
    return loop_class


def get_loop(name: str, config: Optional[Dict] = None) -> Optional[Loop]:
    """Get a loop instance by name.
    
    Args:
        name: Loop name (e.g., "memory", "vision")
        config: Optional config to pass to loop
        
    Returns:
        Loop instance, or None if not found
    """
    if name not in _LOOP_REGISTRY:
        logger.error(f"Loop '{name}' not found in registry")
        return None
    
    # Create instance if needed
    if name not in _LOOP_INSTANCES:
        loop_class = _LOOP_REGISTRY[name]
        _LOOP_INSTANCES[name] = loop_class(config)
        logger.info(f"Created loop instance: {name}")
    
    return _LOOP_INSTANCES[name]


def list_loops() -> List[Dict]:
    """List all registered loops with their capabilities.
    
    Returns:
        List of loop capability dicts (for 120B to understand)
    """
    capabilities = []
    for name, loop_class in _LOOP_REGISTRY.items():
        # Create temp instance just to get capabilities
        try:
            instance = get_loop(name)
            if instance:
                capabilities.append(instance.get_capabilities())
        except Exception as e:
            logger.error(f"Failed to get capabilities for {name}: {e}")
    return capabilities


def get_capabilities_summary() -> str:
    """Get a text summary of all loop capabilities.
    
    This is what we send to 120B so it knows what loops can do.
    Cached to save tokens.
    """
    loops = list_loops()
    if not loops:
        return "No local loops available."
    
    lines = ["Available local loops:"]
    for loop in loops:
        ops = ", ".join(loop.get("supported_operations", []))
        lines.append(f"- {loop['name']}: {loop['description']}")
        if ops:
            lines.append(f"  Operations: {ops}")
    
    return "\n".join(lines)


# Auto-import loop implementations to trigger registration
def _auto_register_loops():
    """Import all loop modules to trigger @register_loop decorators."""
    try:
        from . import memory_loop
        from . import vision_loop
        from . import tool_loop
        from . import computer_loop
    except ImportError as e:
        logger.debug(f"Some loops not yet implemented: {e}")


# Run auto-registration on module load
_auto_register_loops()
