# companion_ai/memory/ai_processor.py — Dedicated AI for memory management

import os
import re
import json
import logging
from dotenv import load_dotenv
from companion_ai.core import config as core_config

try:
    from groq import Groq
except ImportError:
    logging.warning("Groq module not installed")

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GROQ_MEMORY_API_KEY = os.getenv("GROQ_MEMORY_API_KEY")

# Client setup - Dedicated memory processing client
groq_memory_client = None
if GROQ_MEMORY_API_KEY:
    try:
        groq_memory_client = Groq(api_key=GROQ_MEMORY_API_KEY)
        logger.info("Memory AI: Dedicated Groq client initialized")
    except Exception as e:
        logger.error(f"Memory AI initialization failed: {str(e)}")

def _is_valid_fact_key(key: str) -> bool:
    """Whitelist/blacklist gate for extracted fact keys.

    Rejects inferences about mood/behavior and AI self-references.
    Accepts only recognised profile-fact categories.
    """
    k = re.sub(r'[^a-zA-Z0-9]+', '_', key.lower()).strip('_')

    # Blacklist — reject immediately
    _BLACKLIST = [
        r'^user_is_', r'^user_.*ing$', r'^ai_',
        r'conversation', r'aware', r'testing', r'explicit', r'confusion',
    ]
    if any(re.search(pat, k) for pat in _BLACKLIST):
        return False

    # Whitelist — must match at least one
    _WHITELIST = {
        'name', 'age', 'location', 'city', 'country', 'hometown',
        'occupation', 'job', 'work', 'company',
        'hobby', 'hobbies', 'interest', 'interests',
        'favorite', 'preference', 'preferred',
        'skill', 'skills', 'language', 'languages',
        'pet', 'pets', 'project', 'projects',
        'learning', 'studying', 'education',
        'family', 'relationship', 'birthday', 'email', 'phone',
    }
    return any(w in k for w in _WHITELIST)


def generate_memory_response(prompt: str, temperature: float = 0.3, purpose: str = 'summary', importance: float = 0.0) -> str:
    """Generate response using dedicated Groq client for memory tasks."""
    try:
        prefer_fast = (
            core_config.MEMORY_EXTRACT_PREFER_FAST
            and purpose in {'facts', 'extract', 'extraction'}
            and importance < 0.75
        )
        model, is_local, provider = core_config.get_memory_processing_model(task=purpose, prefer_fast=prefer_fast)

        if is_local or provider == 'local':
            from companion_ai.local_llm import LocalLLM

            local_llm = LocalLLM()
            if not local_llm.is_available():
                logger.warning("Memory AI local backend unavailable; falling back to Groq memory route")
            else:
                try:
                    return local_llm.generate(prompt=prompt, model=model).strip()
                except Exception as local_err:
                    logger.warning(f"Memory AI local generation failed; falling back to Groq memory route: {local_err}")

        client = groq_memory_client
        if not client:
            from companion_ai.llm.groq_provider import get_groq_client
            client = get_groq_client()
        if not client:
            return ""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
            max_tokens=512,
            top_p=0.9,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Memory AI generation failed: {str(e)}")
        return ""


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.85:
        return 'high'
    if confidence >= 0.6:
        return 'medium'
    return 'low'


def _format_fact_sentence(key: str, value: str) -> str:
    label = re.sub(r'[_-]+', ' ', key).strip()
    if not label:
        return value.strip()
    return f"User {label} is {value.strip()}"


def _parse_structured_facts(response: str) -> dict:
    if not response:
        return {}

    response_clean = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    json_match = re.search(r'\{.*\}', response_clean, re.DOTALL)
    if not json_match:
        return {}

    raw_json = json_match.group()
    data = json.loads(raw_json)
    facts_list = data.get('facts', [])
    structured: dict = {}

    if isinstance(facts_list, dict):
        for key, item in facts_list.items():
            if not isinstance(item, dict):
                continue
            value = str(item.get('value', '')).strip()
            if not key or not value or not _is_valid_fact_key(key):
                continue
            confidence = float(item.get('confidence', 0.5) or 0.5)
            evidence = item.get('evidence')
            justification = item.get('justification')
            if evidence and len(evidence) > 180:
                evidence = evidence[:177] + '...'
            if justification and len(justification) > 160:
                justification = justification[:157] + '...'
            structured[key] = {
                'value': value,
                'confidence': confidence,
                'conf_label': item.get('conf_label') or _confidence_label(confidence),
                'evidence': evidence,
                'justification': justification,
                'fact': item.get('fact') or _format_fact_sentence(key, value),
            }
        return structured

    if not isinstance(facts_list, list):
        return {}

    for item in facts_list:
        if not isinstance(item, dict):
            continue
        key = item.get('key')
        value = str(item.get('value', '')).strip()
        if not key or not value:
            continue
        if not _is_valid_fact_key(key):
            logger.debug(f"Filtered out fact key: {key}")
            continue
        confidence = float(item.get('confidence', 0.5) or 0.5)
        evidence = item.get('evidence')
        justification = item.get('justification')
        if evidence and len(evidence) > 180:
            evidence = evidence[:177] + '...'
        if justification and len(justification) > 160:
            justification = justification[:157] + '...'
        structured[key] = {
            'value': value,
            'confidence': confidence,
            'conf_label': item.get('conf_label') or _confidence_label(confidence),
            'evidence': evidence,
            'justification': justification,
            'fact': item.get('fact') or _format_fact_sentence(key, value),
        }
    return structured


def extract_profile_facts_from_text(text: str) -> dict:
    """Extract structured profile facts from raw conversation text.

    The extractor prefers facts explicitly stated by the user and uses any AI
    response only as supporting context.
    """
    if not text or not text.strip():
        return {}

    prompt = f"""Extract personal facts explicitly stated or strongly implied by the user.

Prefer facts that are stated by the user directly. Use any AI response only as
supporting context.

Return ONLY valid JSON in this EXACT schema (no markdown, no commentary):
{{
  "facts": [
    {{
      "key": "kebab_case_fact_name",
      "value": "fact value as concise phrase",
      "confidence": 0.0-1.0,
      "conf_label": "high|medium|low",
      "evidence": "exact minimal quote or span from the conversation showing source",
      "justification": "1 short sentence why this is a valid fact"
    }}
  ]
}}

Label guidance:
- high: confidence >= 0.85 and explicitly stated
- medium: 0.6-0.84 or strong preference pattern
- low: < 0.6 or weakly implied

Discard trivia, greetings, and unsupported inferences. Merge duplicates and prefer the most explicit form.

Conversation text:
{text}

JSON:"""

    try:
        response = generate_memory_response(prompt, temperature=0.15, purpose='facts', importance=0.6)
        return _parse_structured_facts(response)
    except Exception as e:
        logger.error(f"Profile fact extraction from text failed: {str(e)}")
        return {}

def analyze_conversation_importance(user_msg: str, ai_msg: str, context: dict) -> float:
    """Analyze how important this conversation is for memory storage."""
    prompt = f"""Analyze this conversation exchange and rate its importance for long-term memory.

IMPORTANCE CRITERIA:
- Personal information revealed (0.7-1.0)
- Emotional significance (0.6-0.9) 
- Unique insights or preferences (0.5-0.8)
- Technical discussions (0.4-0.7)
- Casual greetings (0.1-0.3)
- Simple questions (0.2-0.4)

User: {user_msg}
AI: {ai_msg}

Respond with ONLY the importance score as a decimal number (e.g., 0.7):"""

    try:
        response = generate_memory_response(prompt, temperature=0.1, purpose='summary', importance=0.0)
        logger.info(f"Importance analysis response: {response}")
        
        # Clean response and extract number
        import re
        # Remove thinking tags if present
        clean_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        
        # Look for decimal numbers
        match = re.search(r'(\d*\.?\d+)', clean_response.strip())
        if match:
            score = float(match.group(1))
            # If score is > 1, assume it's out of 10 and convert
            if score > 1.0:
                score = score / 10.0
            return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1
        
        logger.warning(f"Could not extract importance score from: {response}")
    except Exception as e:
        logger.error(f"Importance analysis failed: {e}")
    
    # Fallback: simple heuristic based on message content
    combined_text = f"{user_msg} {ai_msg}".lower()
    
    # High importance indicators
    if any(word in combined_text for word in ['favorite', 'prefer', 'like', 'love', 'hate', 'remember', 'important']):
        return 0.7
    
    # Medium importance indicators  
    if any(word in combined_text for word in ['project', 'work', 'coding', 'programming', 'ai', 'think']):
        return 0.5
    
    # Low importance (greetings, simple responses)
    if any(word in combined_text for word in ['hello', 'hi', 'hey', 'thanks', 'ok', 'yes', 'no']):
        return 0.2
    
    return 0.4  # Default moderate-low importance

def extract_smart_profile_facts(user_msg: str, ai_msg: str) -> dict:
    """Extract structured profile facts with confidence + provenance.

    Returns dict keyed by fact key for backward compatibility:
      {
        "fact_key": {
           "value": str,
           "confidence": float,
           "conf_label": "high|medium|low",
           "evidence": str | None,
           "justification": str | None
        }, ...
      }
    """
    conversation_text = f"User: {user_msg}\nAI: {ai_msg}"
    return extract_profile_facts_from_text(conversation_text)

def generate_smart_summary(user_msg: str, ai_msg: str, importance_score: float) -> str:
    """Generate a contextual summary based on importance."""
    if importance_score < 0.3:
        # Low importance - brief summary
        prompt = f"""Create a brief 1-sentence summary of this low-importance exchange:
User: {user_msg}
AI: {ai_msg}

Summary:"""
    elif importance_score > 0.7:
        # High importance - detailed summary
        prompt = f"""Create a detailed 2-3 sentence summary of this important conversation, capturing key details:
User: {user_msg}
AI: {ai_msg}

Summary:"""
    else:
        # Medium importance - standard summary
        prompt = f"""Summarize this conversation in 1-2 sentences:
User: {user_msg}
AI: {ai_msg}

Summary:"""
    
    return generate_memory_response(prompt, temperature=0.4, purpose='summary', importance=importance_score)

def categorize_insight(insight_text: str) -> str:
    """Categorize an insight for better organization."""
    prompt = f"""Categorize this insight into ONE of these categories:
- personality
- interests
- preferences
- behavior
- emotions
- relationships
- goals
- skills
- general

Insight: {insight_text}

Return ONLY the category name:"""

    response = generate_memory_response(prompt, temperature=0.1, purpose='insight', importance=0.6)
    
    valid_categories = ['personality', 'interests', 'preferences', 'behavior', 
                       'emotions', 'relationships', 'goals', 'skills', 'general']
    
    for category in valid_categories:
        if category in response.lower():
            return category
    
    return 'general'

def generate_contextual_insight(user_msg: str, ai_msg: str, context: dict, importance_score: float) -> str:
    """Generate insights with context awareness."""
    if importance_score < 0.4:
        return ""  # Skip insights for low-importance conversations
    
    prompt = f"""Based on this conversation and context, generate a brief insight about the user's personality, interests, or patterns.

User: {user_msg}
AI: {ai_msg}

Context: {json.dumps(context, indent=2)}
Importance: {importance_score}

Generate a concise insight (1-2 sentences) that reveals something meaningful about the user:"""

    return generate_memory_response(prompt, temperature=0.5)

def enhance_conversation_context(user_msg: str, current_context: dict) -> dict:
    """Enhance conversation context with relevant memories before AI responds."""
    
    # Extract keywords from user message for relevant memory retrieval
    keywords = [word.lower() for word in user_msg.split() if len(word) > 3][:3]
    
    # Import memory functions
    from companion_ai.memory import sqlite_backend as db
    
    # Get relevant memories based on user's current message
    relevant_summaries = db.get_relevant_summaries(keywords, 5)
    relevant_insights = db.get_relevant_insights(keywords, 8)
    all_profile_facts = db.get_all_profile_facts()
    
    # Analyze what additional context might be helpful
    context_analysis_prompt = f"""Analyze this user message and determine what additional context would be most helpful for responding naturally.

User Message: {user_msg}

Available Context:
- Profile Facts: {len(all_profile_facts)} facts available
- Relevant Summaries: {len(relevant_summaries)} summaries found
- Relevant Insights: {len(relevant_insights)} insights found

Current Keywords: {keywords}

Should the AI reference any specific memories or context to respond naturally? 
Respond with 'YES' if specific context is needed, 'NO' if the message is self-contained:"""
    
    try:
        context_needed = generate_memory_response(context_analysis_prompt, temperature=0.2)
        logger.info(f"Context analysis: {context_needed}")
        
        # Build enhanced context (exclude analysis from conversational context)
        enhanced_context = {
            "profile": all_profile_facts,
            "summaries": relevant_summaries,
            "insights": relevant_insights,
            # Don't include context_analysis in conversational context
            "keywords_used": keywords
        }
        
        # Log the analysis separately for debugging
        logger.info(f"Memory analysis result: {context_needed.strip()}")
        
        return enhanced_context
        
    except Exception as e:
        logger.error(f"Context enhancement failed: {e}")
        # Fallback to basic context
        return {
            "profile": all_profile_facts,
            "summaries": relevant_summaries[:3],  # Limit if error
            "insights": relevant_insights[:5],
            "context_analysis": "BASIC",
            "keywords_used": keywords
        }
