# companion_ai/memory_ai.py - Dedicated AI for memory management

import os
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

def generate_memory_response(prompt: str, temperature: float = 0.3, purpose: str = 'summary', importance: float = 0.0) -> str:
    """Generate response using dedicated Groq client for memory tasks."""
    if not groq_memory_client:
        return ""
    
    try:
        model = core_config.choose_model(purpose, importance=importance)
        response = groq_memory_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,  # dynamic model selection
            temperature=temperature,  # Lower temperature for more consistent memory analysis
            max_tokens=512,
            top_p=0.9,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Memory AI generation failed: {str(e)}")
        return ""

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
    """Extract profile facts with confidence scoring."""
    prompt = f"""Extract personal facts about the user from this conversation. For each fact, provide a confidence score (0.0-1.0).

Return ONLY valid JSON in this exact format:
{{
    "facts": {{
        "fact_key": {{"value": "fact_value", "confidence": 0.8}}
    }}
}}

User: {user_msg}
AI: {ai_msg}

Focus on:
- Definitive personal information (high confidence)
- Preferences and interests (medium confidence)
- Implied characteristics (lower confidence)

JSON:"""

    try:
        response = generate_memory_response(prompt, temperature=0.2)
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get('facts', {})
    except Exception as e:
        logger.error(f"Profile fact extraction failed: {str(e)}")
    
    return {}

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
    from companion_ai import memory as db
    
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