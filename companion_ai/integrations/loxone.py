"""
Loxone Smart Home Integration

Controls Loxone Miniserver for lighting via REST API using UUIDs and Moods.
Supports: turn on/off with mood selection, getting status.
"""

import os
import logging
import httpx
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Loxone configuration from .env
LOXONE_HOST = os.getenv("LOXONE_HOST", "192.168.0.200")
LOXONE_USER = os.getenv("LOXONE_USER", "")
LOXONE_PASSWORD = os.getenv("LOXONE_PASSWORD", "")

# Room configuration with UUID and brightness levels
# brightness_on: 100 = Bright (full), 30 = Dim (estimated from Loxone)
ROOM_CONFIG = {
    "bedroom front": {
        "uuid": "10c3dd45-019a-8a3d-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "bedroom rear": {
        "uuid": "10c3dd7e-035c-bb81-ffff01708c6be426",
        "brightness_on": 100,  # Bright only
    },
    "dining room": {
        "uuid": "10e8f3b2-01ae-1079-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "entrance hall": {
        "uuid": "10c95df9-00e9-3b6e-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "kitchen": {
        "uuid": "10c3dce5-01aa-6967-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "landing": {
        "uuid": "10c3d421-0150-3f30-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "living room front": {
        "uuid": "10c3d458-0316-510c-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "living room rear": {
        "uuid": "10c3dd4e-01db-9c0d-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "loft": {
        "uuid": "10e8b9c6-03ae-9fa2-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
    "loft landing": {
        "uuid": "10c3dd33-015d-795b-ffff01708c6be426",
        "brightness_on": 30,  # Dim mode
    },
}

# Aliases for natural language
ROOM_ALIASES = {
    "dining": "dining room",
    "entrance": "entrance hall",
    "living room": "living room front",
    "bedroom": "bedroom rear",  # Default to rear
}

# Central lighting controller for "all lights"
CENTRAL_CONTROLLER_UUID = "123be292-011c-7ac9-fffff4e831588be6"

def _get_base_url() -> str:
    """Get Loxone API base URL with auth."""
    return f"http://{LOXONE_USER}:{LOXONE_PASSWORD}@{LOXONE_HOST}"

def _get_room_config(room_query: str) -> Optional[Dict]:
    """Get room config for a room name."""
    if not room_query:
        return None
    
    room_lower = room_query.lower().strip()
    
    # Check aliases first
    if room_lower in ROOM_ALIASES:
        room_lower = ROOM_ALIASES[room_lower]
    
    # Exact match
    if room_lower in ROOM_CONFIG:
        return {"name": room_lower, **ROOM_CONFIG[room_lower]}
    
    # Partial match
    for key, config in ROOM_CONFIG.items():
        if key in room_lower or room_lower in key:
            return {"name": key, **config}
    
    return None

async def turn_on_lights(room: Optional[str] = None) -> Dict[str, Any]:
    """
    Turn on lights in specified room using dimmer sub-controls.
    Sets AI1 and AI2 dimmers to room's configured brightness level.
    """
    if not LOXONE_USER or not LOXONE_PASSWORD:
        return {"success": False, "error": "Loxone credentials not configured"}
    
    if not room:
        return {
            "success": False, 
            "error": "Please specify which room to turn on",
            "available_rooms": list(ROOM_CONFIG.keys())
        }
    
    base_url = _get_base_url()
    
    # Handle "all lights"
    if room.lower() in ["all", "all lights", "everything"]:
        # For all lights, iterate through all rooms
        async with httpx.AsyncClient(timeout=10.0) as client:
            for room_name, config in ROOM_CONFIG.items():
                uuid = config["uuid"]
                brightness = config.get("brightness_on", 100)
                for sub in ["AI1", "AI2"]:
                    url = f"{base_url}/jdev/sps/io/{uuid}/{sub}/{brightness}"
                    try:
                        await client.get(url)
                    except:
                        pass
        return {"success": True, "room": "all", "status": "on", "message": "Turned on all lights"}
    
    config = _get_room_config(room)
    if not config:
        return {"success": False, "error": f"Unknown room: {room}"}
    
    uuid = config["uuid"]
    room_name = config["name"]
    brightness = config.get("brightness_on", 100)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            success = False
            # Turn on AI1 and AI2 dimmers to configured brightness
            for sub in ["AI1", "AI2"]:
                url = f"{base_url}/jdev/sps/io/{uuid}/{sub}/{brightness}"
                response = await client.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("LL", {}).get("value") == "1":
                        success = True
            
            if success:
                logger.info(f"✅ Turned on {room_name} at {brightness}%")
                return {
                    "success": True, 
                    "room": room_name, 
                    "brightness": brightness,
                    "status": "on", 
                    "message": f"Turned on {room_name} lights at {brightness}%"
                }
            else:
                return {"success": False, "error": "Dimmer command failed"}
        except Exception as e:
            logger.error(f"❌ Error turning on {room_name}: {e}")
            return {"success": False, "error": str(e)}

async def turn_off_lights(room: Optional[str] = None) -> Dict[str, Any]:
    """Turn off lights using dimmer sub-controls (set to 0)."""
    if not LOXONE_USER or not LOXONE_PASSWORD:
        return {"success": False, "error": "Loxone credentials not configured"}
    
    if not room:
        return {"success": False, "error": "Please specify which room to turn off"}
    
    base_url = _get_base_url()
    
    # Handle "all lights"
    if room.lower() in ["all", "all lights", "everything"]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for room_name, config in ROOM_CONFIG.items():
                uuid = config["uuid"]
                for sub in ["AI1", "AI2"]:
                    url = f"{base_url}/jdev/sps/io/{uuid}/{sub}/0"
                    try:
                        await client.get(url)
                    except:
                        pass
        return {"success": True, "room": "all", "status": "off", "message": "Turned off all lights"}
    
    config = _get_room_config(room)
    if not config:
        return {"success": False, "error": f"Unknown room: {room}"}
    
    uuid = config["uuid"]
    room_name = config["name"]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Turn off AI1 and AI2 dimmers (set to 0)
            for sub in ["AI1", "AI2"]:
                url = f"{base_url}/jdev/sps/io/{uuid}/{sub}/0"
                await client.get(url)
            
            logger.info(f"✅ Turned off: {room_name}")
            return {"success": True, "room": room_name, "status": "off", "message": f"Turned off {room_name} lights"}
        except Exception as e:
            logger.error(f"❌ Error turning off {room_name}: {e}")
            return {"success": False, "error": str(e)}

async def set_brightness(room: str, brightness: int) -> Dict[str, Any]:
    """Set a specific brightness level for a room (0-100)."""
    if not LOXONE_USER or not LOXONE_PASSWORD:
        return {"success": False, "error": "Loxone credentials not configured"}
    
    if not room:
        return {"success": False, "error": "Please specify which room"}
    
    brightness = max(0, min(100, brightness))  # Clamp to 0-100
    
    config = _get_room_config(room)
    if not config:
        return {"success": False, "error": f"Unknown room: {room}"}
    
    uuid = config["uuid"]
    room_name = config["name"]
    base_url = _get_base_url()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            for sub in ["AI1", "AI2"]:
                url = f"{base_url}/jdev/sps/io/{uuid}/{sub}/{brightness}"
                await client.get(url)
            
            mode = "bright" if brightness >= 80 else "dim" if brightness > 0 else "off"
            logger.info(f"✅ Set {room_name} to {brightness}% ({mode})")
            return {
                "success": True, 
                "room": room_name, 
                "brightness": brightness,
                "mode": mode,
                "message": f"Set {room_name} to {brightness}%"
            }
        except Exception as e:
            logger.error(f"❌ Error setting brightness for {room_name}: {e}")
            return {"success": False, "error": str(e)}

async def get_room_statuses() -> Dict[str, Any]:
    """Get current status of all rooms for the control center UI."""
    if not LOXONE_USER or not LOXONE_PASSWORD:
        return {"success": False, "error": "Loxone credentials not configured"}
    
    base_url = _get_base_url()
    statuses = []
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            for room_name, config in ROOM_CONFIG.items():
                uuid = config["uuid"]
                display_name = room_name.title()
                brightness_on = config.get("brightness_on", 100)
                supports_dim = brightness_on < 100  # If configured for <100, supports dim
                
                # Fetch live state using /all endpoint
                brightness = 0
                try:
                    url = f"{base_url}/jdev/sps/io/{uuid}/all"
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json().get("LL", {})
                        value_str = data.get("value", "0")
                        try:
                            brightness = int(float(value_str))
                        except:
                            brightness = 0
                except:
                    brightness = 0
                
                # Determine mode based on brightness
                if brightness == 0:
                    status = "off"
                    mode = "off"
                elif brightness >= 80:
                    status = "on"
                    mode = "bright"
                else:
                    status = "on"
                    mode = "dim"
                
                statuses.append({
                    "id": room_name,
                    "name": display_name,
                    "uuid": uuid,
                    "status": status,
                    "brightness": brightness,
                    "mode": mode,
                    "supports_dim": supports_dim
                })
            
            return {"success": True, "rooms": statuses}
        except Exception as e:
            logger.error(f"Error getting room statuses: {e}")
            return {"success": False, "error": str(e)}

async def get_available_rooms() -> Dict[str, Any]:
    """Get list of available room names."""
    return {
        "success": True,
        "rooms": list(ROOM_CONFIG.keys()),
        "message": "Available rooms: " + ", ".join(ROOM_CONFIG.keys())
    }

async def test_connection() -> Dict[str, Any]:
    """Test connection to Loxone Miniserver."""
    if not LOXONE_USER or not LOXONE_PASSWORD:
        return {"success": False, "error": "Loxone credentials not configured"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"http://{LOXONE_USER}:{LOXONE_PASSWORD}@{LOXONE_HOST}/jdev/cfg/api"
            response = await client.get(url)
            
            if response.status_code == 200:
                return {"success": True, "message": "Connected to Loxone Miniserver!"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
