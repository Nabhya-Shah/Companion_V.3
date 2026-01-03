"""
Integrations package for external services.
"""

from .loxone import (
    turn_on_lights,
    turn_off_lights,
    get_room_statuses,
    get_available_rooms,
    test_connection as test_loxone
)

__all__ = [
    "turn_on_lights",
    "turn_off_lights", 
    "get_room_statuses",
    "get_available_rooms",
    "test_loxone"
]
