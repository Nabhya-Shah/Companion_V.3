# companion_ai/llm/memory_extraction.py
"""Memory-oriented LLM calls — summaries, fact extraction, insights.

These functions are called by the memory subsystem to process conversation
content via the Groq (or local) API.
"""

import json
import re
import logging

from companion_ai.core import config as core_config
from companion_ai.llm.groq_provider import groq_client, generate_groq_response

logger = logging.getLogger(__name__)


# --- Memory Processing Functions ---

def generate_summary(user_msg: str, ai_msg: str) -> str:
    """Generate a conversation summary"""
    prompt = f"""Summarize this conversation exchange in 1-2 sentences:
User: {user_msg}
AI: {ai_msg}

Summary:"""

    try:
        if groq_client:
            model = core_config.choose_model('summary', importance=0.5)
            logger.debug(f"generate_summary using model={model}")
            return generate_groq_response(prompt, model=model)
    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
    return ""


def extract_profile_facts(user_msg: str, ai_msg: str) -> dict:
    """Extract explicit user-stated profile facts (structured output if available).

    Fallback path keeps legacy parsing to remain robust if structured outputs unsupported.
    """
    if not groq_client:
        return {}
    model = core_config.choose_model('facts')
    logger.debug(f"extract_profile_facts using model={model}")

    # Structured outputs attempt
    if core_config.ENABLE_STRUCTURED_FACTS:
        try:
            # Use standard JSON mode which is supported by 120B and others
            # This is more robust than regex but less strict than json_schema
            prompt = (
                "Extract explicit user facts into a JSON object. Keys should be fact types (name, age, hobby, etc), values should be the fact.\n"
                "Return ONLY the JSON object. If no facts, return {}.\n"
                f"User: {user_msg}\nAssistant: {ai_msg}"
            )

            resp = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a JSON extractor. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            raw_json = resp.choices[0].message.content
            if raw_json:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    return _filter_fact_dict(parsed, user_msg)

        except Exception as se:
            logger.debug(f"Structured fact extraction failed: {se}; falling back")

    # Legacy fallback path with improved prompt
    prompt = (
        "Extract ONLY explicit facts the user DIRECTLY STATED about themselves.\n\n"
        f'USER MESSAGE: "{user_msg}"\n\n'
        "CRITICAL RULES:\n"
        "1. ONLY extract facts the user explicitly said with their own words\n"
        "2. Do NOT infer mood, behavior, or personality (no 'user is chill', 'user is quiet', etc.)\n"
        "3. Do NOT extract conversation meta-facts (no 'user is talking to AI', 'AI is repeating', etc.)\n"
        "4. Do NOT make assumptions or interpretations\n"
        "5. If no explicit facts, return empty: {}\n\n"
        "ALLOWED fact types: name, age, location, occupation, hobbies, preferences, skills, interests, family, pets, projects, education\n\n"
        "CORRECT Examples:\n"
        '- "My name is John" → {"name": "John"}\n'
        '- "I love Python" → {"favorite_language": "Python"}\n'
        '- "I\'m 25 years old" → {"age": "25"}\n'
        '- "I work as a teacher" → {"occupation": "teacher"}\n'
        '- "I\'m learning Japanese and enjoy hiking" → {"learning": "Japanese", "hobby": "hiking"}\n\n'
        "WRONG Examples (DO NOT extract these):\n"
        '- "Yeah I\'m chill" → {} (mood/behavior, not a fact)\n'
        '- "Nothing much" → {} (no facts stated)\n'
        '- "Lol yeah" → {} (no facts stated)\n'
        '- User seems quiet → NEVER extract inferences!\n\n'
        "Return ONLY a valid JSON object:"
    )
    try:
        response = generate_groq_response(prompt, model=model)
        if not response:
            return {}

        # Clean up response - strip markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code block
            lines = response.split('\n')
            response = '\n'.join(lines[1:-1]) if len(lines) > 2 else response
            response = response.replace("```json", "").replace("```", "").strip()

        # Try to extract JSON if there's extra text
        if not response.startswith('{'):
            # Look for JSON object in the response
            json_match = re.search(r'\{[^}]*\}', response)
            if json_match:
                response = json_match.group(0)
            else:
                logger.warning(f"No JSON found in fact extraction response: {response[:100]}")
                return {}

        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            return {}

        filtered = _filter_fact_dict(parsed, user_msg)
        if filtered:
            logger.info(f"Successfully extracted {len(filtered)} facts: {list(filtered.keys())}")
        return filtered

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in fact extraction: {e}. Response was: {response[:200] if response else 'empty'}")
        return {}
    except Exception as e:
        logger.error(f"Profile fact extraction failed: {e}")
        return {}


def _filter_fact_dict(parsed: dict, user_msg: str) -> dict:
    """Apply STRICT filtering - ONLY allow facts explicitly stated by user.

    Rejects:
    - Inferences about mood/behavior (user_is_chill, user_is_quiet, etc.)
    - AI self-references (ai_is_repeating_itself, ai_is_here_to_help)
    - Conversation meta-facts (user_is_talking_to_ai, previous_conversations)
    """
    user_lower = user_msg.lower()
    filtered: dict[str, str] = {}

    def norm_key(k: str) -> str:
        k2 = re.sub(r'[^a-zA-Z0-9]+', '_', k.lower()).strip('_')
        k2 = re.sub(r'_+', '_', k2)
        return k2[:60]

    # Blacklist patterns - reject ANY key matching these
    blacklist_patterns = [
        r'^user_is_',      # user_is_chill, user_is_quiet, etc.
        r'^user_.*ing$',   # user_chilling, user_testing, etc.
        r'^ai_',           # ai_is_repeating_itself, etc.
        r'conversation',   # previous_conversations, etc.
        r'aware',          # user_is_aware_of_ai, etc.
        r'testing',        # user_is_testing_ai
        r'explicit',       # user_explicit_interest
        r'confusion',      # user_confusion
    ]

    # Whitelist - ONLY these fact types allowed
    allowed_fact_types = [
        'name', 'age', 'location', 'city', 'country', 'hometown',
        'occupation', 'job', 'work', 'company',
        'hobby', 'hobbies', 'interest', 'interests',
        'favorite_game', 'favorite_movie', 'favorite_food', 'favorite_drink', 'favorite_snack',
        'favorite_color', 'favorite_book', 'favorite_music', 'favorite_band',
        'skill', 'skills', 'language', 'languages',
        'pet', 'pets', 'project', 'projects',
        'learning', 'studying', 'education',
        'family', 'relationship',
    ]

    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, (str, int, float)):
            continue
        v_str = str(v).strip()
        k_str = k.strip()
        if not k_str or not v_str:
            continue

        key_normalized = norm_key(k_str)

        # REJECT if matches blacklist
        if any(re.search(pattern, key_normalized) for pattern in blacklist_patterns):
            logger.debug(f"Rejected blacklisted fact: {key_normalized}")
            continue

        # REQUIRE that key is in whitelist OR value appears in user message
        key_lower = k_str.lower()
        value_lower = v_str.lower()

        # Check if key type is whitelisted
        is_whitelisted = any(allowed in key_lower for allowed in allowed_fact_types)

        # Check if value literally appears in user message
        value_in_message = value_lower in user_lower

        # ONLY accept if whitelisted AND value is in message
        if is_whitelisted and value_in_message:
            filtered[key_normalized] = v_str[:160]
            logger.debug(f"Accepted fact: {key_normalized} = {v_str}")
        else:
            logger.debug(f"Rejected fact: {key_normalized} (whitelisted:{is_whitelisted}, in_msg:{value_in_message})")

    return filtered


def generate_insight(user_msg: str, ai_msg: str, context: dict) -> str:
    """Generate insights about the user or conversation"""
    prompt = f"""Based on this conversation and context, generate a brief insight about the user's interests, mood, or patterns:
User: {user_msg}
AI: {ai_msg}

Context: {context}

Insight:"""

    try:
        if groq_client:
            model = core_config.choose_model('insight', importance=0.6)
            logger.debug(f"generate_insight using model={model}")
            return generate_groq_response(prompt, model=model)
    except Exception as e:
        logger.error(f"Insight generation failed: {str(e)}")
    return ""
