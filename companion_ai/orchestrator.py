# companion_ai/orchestrator.py
"""
120B Orchestrator - The Brain of Companion AI V6

The orchestrator:
1. Receives user message
2. Decides: answer directly OR delegate to local loop
3. Handles loop responses
4. Decides what to save to memory (AFTER response)
5. Returns final user-facing response

120B NEVER shows its internal routing decisions to the user.
"""

import logging
import json
import asyncio
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from companion_ai.core import config as core_config
from companion_ai.local_loops import get_loop, get_capabilities_summary, LoopResult

logger = logging.getLogger(__name__)


class OrchestratorAction(Enum):
    """Actions the orchestrator can take."""
    ANSWER = "answer"          # Respond directly
    DELEGATE = "delegate"      # Call a local loop
    BACKGROUND = "background"  # Start background task
    MEMORY_SEARCH = "memory_search"  # Quick memory lookup


@dataclass
class OrchestratorDecision:
    """Structured decision from 120B.
    
    This is INTERNAL - never shown to user.
    """
    action: OrchestratorAction
    content: Optional[str] = None      # For ANSWER
    loop: Optional[str] = None         # For DELEGATE/BACKGROUND
    task: Optional[Dict] = None        # Task details for loop
    save_facts: List[str] = None       # Facts to save after response
    
    @classmethod
    def from_json(cls, json_str: str) -> "OrchestratorDecision":
        """Parse decision from JSON string."""
        try:
            # Try to extract JSON from markdown code blocks if present
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            data = json.loads(json_str)
            logger.info(f"✅ DEBUG: Parsed JSON successfully: action={data.get('action')}, loop={data.get('loop')}")
            return cls(
                action=OrchestratorAction(data.get("action", "answer")),
                content=data.get("content"),
                loop=data.get("loop"),
                task=data.get("task"),
                save_facts=data.get("save_facts", [])
            )
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to parse orchestrator decision: {e}")
            logger.error(f"❌ DEBUG: Raw input was: {json_str[:200]}...")
            # Fallback to treating entire response as answer
            return cls(action=OrchestratorAction.ANSWER, content=json_str)

class Orchestrator:
    """The 120B brain that orchestrates local loops.
    
    Uses Groq 120B for main orchestration decisions.
    Local Ollama models are used for loop execution (not orchestration).
    """
    
    def __init__(self):
        self._capabilities_cache = None
        self._groq_client = None
    
    def _get_groq_client(self):
        """Get Groq client for 120B orchestration."""
        if not self._groq_client:
            from companion_ai.llm_interface import get_groq_client
            self._groq_client = get_groq_client()
        return self._groq_client
    
    def _get_client_and_model(self):
        """Get the Groq client and 120B model for orchestration.
        
        The main orchestrator ALWAYS uses Groq 120B.
        Local Ollama models are only used within loops.
        Returns (client, model_name, is_local=False)
        """
        groq_client = self._get_groq_client()
        if groq_client:
            return groq_client, core_config.PRIMARY_MODEL, False
        
        return None, None, False
    
    def _get_capabilities(self) -> str:
        """Get cached loop capabilities string."""
        if not self._capabilities_cache:
            self._capabilities_cache = get_capabilities_summary()
        return self._capabilities_cache
    
    def _build_orchestrator_prompt(self, user_message: str, context: Dict) -> str:
        """Build system prompt for 120B routing decision.
        
        This prompt tells 120B about available loops and how to decide.
        """
        capabilities = self._get_capabilities()
        recent_context = context.get("recent_conversation", "")[:1000]  # Limit context
        
        return f"""You are the Companion AI orchestrator. You decide how to handle each user message.

## Available Local Loops
{capabilities}

## Your Decision Format
You MUST respond with a JSON object (no markdown, just JSON):

For direct answers (greetings, conversation, questions you can answer):
{{"action": "answer", "content": "Your response here"}}

For delegating to tools loop (time, math, simple lookups):
{{"action": "delegate", "loop": "tools", "task": {{"operation": "get_time"}}}}
{{"action": "delegate", "loop": "tools", "task": {{"operation": "calculate", "expression": "2+2"}}}}
{{"action": "delegate", "loop": "tools", "task": {{"operation": "brain_list", "subdir": ""}}}}
{{"action": "delegate", "loop": "tools", "task": {{"operation": "brain_read", "path": "notes/file.md"}}}}

For delegating to memory loop (recalling user facts):
{{"action": "delegate", "loop": "memory", "task": {{"operation": "search", "query": "user name"}}}}

For delegating to vision loop (looking at screen):
{{"action": "delegate", "loop": "vision", "task": {{"operation": "describe"}}}}
{{"action": "delegate", "loop": "vision", "task": {{"operation": "find", "element": "submit button"}}}}

For background tasks (long-running automation only):
{{"action": "background", "loop": "computer", "task": {{"operation": "execute", "task": "..."}}}}

## IMPORTANT Routing Rules
## MEMORY & PERSONALIZATION:
- "Remember that X", "Memorize this" → DELEGATE to memory loop (mem0_add)
- "I prefer X", "My favorite Y is Z", "I am [Context]" → DELEGATE to memory loop (mem0_add)
- "What do you know about me?", "Who am I?" → DELEGATE to memory loop (mem0_get)
- "Forget that X" → DELEGATE to memory loop (mem0_delete)
- "What time is it?" → DELEGATE to tools loop with get_time (NOT background!)
- "What's 2+2?" → DELEGATE to tools loop with calculate
- "What's my name?" → DELEGATE to memory loop
- "Look at my screen" → DELEGATE to vision loop
- "Hi", "Hello", questions about general topics → ANSWER directly

**BROWSER AUTOMATION (uses Playwright - fast & reliable):**
- "Go to google.com" → DELEGATE to tools loop (browser_goto)
- "Open bookmark X", "Open [Name] (e.g. Open Bromcom)" → DELEGATE to tools loop (open_bookmark)
- "Go to google.com" → DELEGATE to tools loop (browser_goto)
- "Save this page as X", "Bookmark this" → DELEGATE to tools loop (add_bookmark)
- "Open wikipedia", "Open a new tab", "Open Chrome tab" → DELEGATE to tools loop (browser_goto url="about:blank")
- "Click the login button" → DELEGATE to tools loop (browser_click)
- "Type my email" → DELEGATE to tools loop (browser_type)
- "Enable browser control", "Restart Chrome for AI", "Fix Chrome" → DELEGATE to tools loop (enable_browser_control)
- ANY web browsing task → DELEGATE to tools loop

**DESKTOP AUTOMATION (slower, uses vision):**
- "Open notepad" → BACKGROUND computer loop
- "Click on desktop icon" → BACKGROUND computer loop
- ONLY use computer loop for non-browser desktop tasks (e.g. Spotify, Discord, Explorer)

## Detecting Facts to Save
If the user shares personal info (name, preferences, facts about themselves), add:
"save_facts": ["User's name is X", "User likes Y"]

Only save CONCRETE facts, not casual chat.

## Recent Context
{recent_context if recent_context else "No prior context."}
"""
    
    async def process(
        self, 
        user_message: str,
        context: Optional[Dict] = None
    ) -> Tuple[str, Optional[Dict]]:
        """Process a user message and return response.
        
        Args:
            user_message: The user's input
            context: Optional context (conversation history, etc.)
            
        Returns:
            Tuple of (response_text, metadata)
        """
        context = context or {}
        
        try:
            # Step 1: Get 120B decision
            decision = await self._get_decision(user_message, context)
            
            # Step 2: Execute decision
            response, metadata = await self._execute_decision(decision, user_message, context)
            
            # Step 3: Handle memory saving (AFTER response is generated)
            if decision.save_facts:
                await self._save_facts(decision.save_facts)
            
            return response, metadata
            
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            return f"I encountered an error: {str(e)}", {"error": True}
    
    async def _get_decision(self, user_message: str, context: Dict) -> OrchestratorDecision:
        """Get routing decision from local model (or Groq fallback)."""
        client, model, is_local = self._get_client_and_model()
        if not client:
            # Fallback to direct answer if no client
            return OrchestratorDecision(
                action=OrchestratorAction.ANSWER,
                content="I'm having trouble connecting to my brain. Please try again."
            )
        
        system_prompt = self._build_orchestrator_prompt(user_message, context)
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,  # Lower temp for consistent routing
                max_tokens=1000
            )
            
            raw_response = response.choices[0].message.content.strip()
            
            # DEBUG: Log the raw response from 120B
            logger.info(f"🔍 DEBUG: 120B raw response:\n{raw_response[:500]}...")
            
            # Log tokens
            from companion_ai.llm_interface import log_tokens
            log_tokens(
                model,
                response.usage.prompt_tokens if response.usage else 0,
                response.usage.completion_tokens if response.usage else 0,
                f"orchestrator_routing_{'local' if is_local else 'groq'}"
            )
            
            # Parse decision
            decision = OrchestratorDecision.from_json(raw_response)
            
            # DEBUG: Log the parsed decision
            logger.info(f"🎯 DEBUG: Parsed decision: action={decision.action}, loop={decision.loop}, has_content={decision.content is not None}")
            
            return decision
            
        except Exception as e:
            logger.error(f"Failed to get orchestrator decision: {e}")
            # Fallback: try direct answer
            return OrchestratorDecision(
                action=OrchestratorAction.ANSWER,
                content=None  # Will need to call model again for response
            )
    
    async def _execute_decision(
        self, 
        decision: OrchestratorDecision,
        user_message: str,
        context: Dict
    ) -> Tuple[str, Dict]:
        """Execute the orchestrator's decision."""
        
        if decision.action == OrchestratorAction.ANSWER:
            if decision.content:
                return decision.content, {"source": "120b_direct"}
            else:
                # Need to generate response (fallback path)
                return await self._generate_direct_response(user_message, context)
        
        elif decision.action == OrchestratorAction.DELEGATE:
            return await self._handle_delegation(decision, user_message, context)
        
        elif decision.action == OrchestratorAction.BACKGROUND:
            return await self._handle_background(decision)
        
        elif decision.action == OrchestratorAction.MEMORY_SEARCH:
            return await self._handle_memory_search(decision, user_message, context)
        
        else:
            logger.warning(f"Unknown action: {decision.action}")
            return await self._generate_direct_response(user_message, context)
    
    async def _handle_delegation(
        self, 
        decision: OrchestratorDecision,
        user_message: str,
        context: Dict
    ) -> Tuple[str, Dict]:
        """Handle delegation to a local loop."""
        loop_name = decision.loop
        task = decision.task or {}
        
        # DEBUG: Log delegation attempt
        logger.info(f"🔄 DEBUG: Delegating to loop '{loop_name}' with task: {task}")
        
        loop = get_loop(loop_name)
        if not loop:
            logger.error(f"❌ DEBUG: Loop not found: {loop_name}")
            return await self._generate_direct_response(user_message, context)
        
        logger.info(f"✅ DEBUG: Got loop instance: {loop}")
        
        try:
            # Execute loop
            logger.info(f"🚀 DEBUG: Executing loop.execute({task})")
            result = await loop.execute(task)
            
            if result.status.value == "error":
                logger.error(f"Loop {loop_name} failed: {result.error}")
                return await self._generate_direct_response(user_message, context)
            
            # Synthesize response with loop result
            response = await self._synthesize_response(
                user_message, 
                loop_name, 
                result.data, 
                context
            )
            
            return response, {
                "source": f"loop_{loop_name}",
                "loop_result": result.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Loop execution failed: {e}")
            return await self._generate_direct_response(user_message, context)
    
    async def _handle_background(self, decision: OrchestratorDecision) -> Tuple[str, Dict]:
        """Handle background task delegation."""
        loop_name = decision.loop
        task = decision.task or {}
        
        loop = get_loop(loop_name)
        if not loop:
            return "I can't start that background task right now.", {"error": True}
        
        try:
            result = await loop.execute(task)
            
            if result.status.value == "success":
                task_id = result.data.get("task_id", "unknown")
                return (
                    f"I'm working on that! Check the tasks panel on the left for progress. (Task ID: {task_id})",
                    {"source": "background", "task_id": task_id}
                )
            else:
                return "I couldn't start that task. Please try again.", {"error": True}
                
        except Exception as e:
            logger.error(f"Background task failed: {e}")
            return "Something went wrong starting that task.", {"error": True}
    
    async def _handle_memory_search(
        self, 
        decision: OrchestratorDecision,
        user_message: str,
        context: Dict
    ) -> Tuple[str, Dict]:
        """Quick memory search and response."""
        task = decision.task or {"operation": "search", "query": user_message}
        
        loop = get_loop("memory")
        if not loop:
            return await self._generate_direct_response(user_message, context)
        
        result = await loop.execute(task)
        
        # Synthesize with memory results
        return await self._synthesize_response(
            user_message,
            "memory",
            result.data,
            context
        )
    
    async def _generate_direct_response(
        self, 
        user_message: str, 
        context: Dict
    ) -> Tuple[str, Dict]:
        """Generate a direct response without loops (fallback)."""
        client, model, is_local = self._get_client_and_model()
        if not client:
            return "I'm having connection issues.", {"error": True}
        
        try:
            from companion_ai.core.context_builder import build_system_prompt_with_meta
            
            # Fix: pass user_message and recent_conversation, extract system_prompt from result
            recent_conversation = context.get("recent_conversation", "")
            result = build_system_prompt_with_meta(user_message, recent_conversation)
            system_prompt = result.get("system_prompt", "")
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            source = "local_direct" if is_local else "groq_fallback"
            return response.choices[0].message.content, {"source": source}
            
        except Exception as e:
            logger.error(f"Direct response failed: {e}")
            return "Sorry, I'm having trouble responding right now.", {"error": True}
    
    async def _synthesize_response(
        self, 
        user_message: str,
        loop_name: str,
        loop_data: Any,
        context: Dict
    ) -> str:
        """Use local model to synthesize a response from loop output."""
        client, model, is_local = self._get_client_and_model()
        if not client:
            # Best effort response
            return f"Here's what I found: {loop_data}"
        
        synthesis_prompt = f"""You are Companion AI. Synthesize a natural response.

User asked: {user_message}

The {loop_name} loop returned this data:
{json.dumps(loop_data, indent=2)}

Respond naturally as if you found this information yourself. 
Don't mention "loops" or technical details. Be conversational."""
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": synthesis_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            logger.info(f"Synthesis via {'local' if is_local else 'groq'}")
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"Based on what I found: {loop_data}"
    
    async def _save_facts(self, facts: List[str]):
        """Save facts to memory via Memory Loop."""
        if not facts:
            return
        
        loop = get_loop("memory")
        if not loop:
            logger.warning("Memory loop not available for saving facts")
            return
        
        for fact in facts:
            try:
                await loop.execute({"operation": "save", "fact": fact})
                logger.info(f"Saved fact: {fact}")
            except Exception as e:
                logger.error(f"Failed to save fact '{fact}': {e}")


# Singleton instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get the singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


async def process_message_async(user_message: str, context: Optional[Dict] = None) -> Tuple[str, Dict]:
    """Async convenience function to process a message through the orchestrator."""
    orchestrator = get_orchestrator()
    return await orchestrator.process(user_message, context)


def process_message(user_message: str, context: Optional[Dict] = None) -> Tuple[str, Dict]:
    """Sync wrapper for process_message_async.
    
    Use this from non-async code (like Flask views or generators).
    """
    import asyncio
    
    try:
        # Try to get the running loop
        loop = asyncio.get_running_loop()
        # If we're already in an async context, run in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, process_message_async(user_message, context))
            return future.result(timeout=120)  # 2 minute timeout
    except RuntimeError:
        # No running loop - we can use asyncio.run directly
        return asyncio.run(process_message_async(user_message, context))
