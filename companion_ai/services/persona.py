import os
import yaml
import logging
import threading
import json
from datetime import datetime
from typing import List, Dict, Any

from companion_ai.llm_interface import generate_model_response

logger = logging.getLogger(__name__)

# Path to the traits file
TRAITS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'companion_brain', 'system', 'learned_traits.yaml')

def ensure_traits_file():
    """Ensure the traits file exists with default content."""
    if not os.path.exists(TRAITS_FILE):
        try:
            os.makedirs(os.path.dirname(TRAITS_FILE), exist_ok=True)
            default_data = {
                "last_updated": datetime.now().isoformat(),
                "user_style": [],
                "evolved_traits": [],
                "rapport_level": "Neutral"
            }
            with open(TRAITS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(default_data, f)
        except Exception as e:
            logger.error(f"Failed to create traits file: {e}")

def load_traits() -> Dict[str, Any]:
    """Load learned traits from file."""
    ensure_traits_file()
    try:
        if os.path.exists(TRAITS_FILE):
            with open(TRAITS_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load traits: {e}")
    return {}

def save_traits(data: Dict[str, Any]):
    """Save learned traits to file."""
    try:
        os.makedirs(os.path.dirname(TRAITS_FILE), exist_ok=True)
        with open(TRAITS_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
        logger.info("✅ Updated learned traits")
    except Exception as e:
        logger.error(f"Failed to save traits: {e}")

def analyze_and_evolve(history: List[Dict[str, str]]):
    """Analyze conversation history and update traits (Run in background)."""
    if not history:
        return

    logger.info("🧠 Starting persona evolution analysis...")
    
    # Format history for the prompt (last 20 turns)
    history_text = ""
    for turn in history[-20:]: 
        user_text = turn.get('user', '')
        ai_text = turn.get('ai', '')
        # Truncate very long messages to save tokens
        if len(user_text) > 500: user_text = user_text[:500] + "..."
        if len(ai_text) > 500: ai_text = ai_text[:500] + "..."
        history_text += f"User: {user_text}\nAI: {ai_text}\n"

    current_traits = load_traits()
    
    prompt = f"""
    Analyze the following conversation history between a User and an AI Companion.
    
    Current Perception:
    - User Style: {current_traits.get('user_style', [])}
    - Evolved Traits: {current_traits.get('evolved_traits', [])}
    - Rapport: {current_traits.get('rapport_level', 'Unknown')}
    
    Task:
    1. Analyze the User's communication style (tone, length, technicality, emoji use).
    2. Determine how the AI should adapt its personality to serve this specific user better.
    3. Assess the current rapport level.
    
    Return ONLY a JSON object with this structure:
    {{
        "user_style": ["trait1", "trait2", ...],
        "evolved_traits": ["trait1", "trait2", ...],
        "rapport_level": "Description"
    }}
    
    Conversation History:
    {history_text}
    """
    
    try:
        # Use 8B model for fast analysis
        # We use a simple system prompt to enforce JSON
        response = generate_model_response(
            prompt, 
            system_prompt="You are an expert psychologist and conversation analyst. Output valid JSON only. Do not include markdown formatting.", 
            model="llama-3.1-8b-instant"
        )
        
        # Parse JSON (robust extraction)
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = response[start:end]
            new_data = json.loads(json_str)
            
            # Update and save
            final_data = {
                "last_updated": datetime.now().isoformat(),
                "user_style": new_data.get("user_style", []),
                "evolved_traits": new_data.get("evolved_traits", []),
                "rapport_level": new_data.get("rapport_level", "Neutral")
            }
            save_traits(final_data)
        else:
            logger.warning(f"Could not parse JSON from evolution response: {response[:100]}...")
            
    except Exception as e:
        logger.error(f"Persona evolution failed: {e}")

def trigger_evolution_background(history: List[Dict[str, str]]):
    """Trigger analysis in a background thread."""
    thread = threading.Thread(target=analyze_and_evolve, args=(history,))
    thread.daemon = True
    thread.start()
