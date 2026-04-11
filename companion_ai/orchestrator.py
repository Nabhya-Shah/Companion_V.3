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
import re
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
    PLAN = "plan"              # Multi-step plan execution


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
    plan_steps: Optional[List[Dict]] = None  # For PLAN — ordered steps
    
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
            logger.info(f"DEBUG: Parsed JSON successfully: action={data.get('action')}, loop={data.get('loop')}")
            return cls(
                action=OrchestratorAction(data.get("action", "answer")),
                content=data.get("content"),
                loop=data.get("loop"),
                task=data.get("task"),
                save_facts=data.get("save_facts", []),
                plan_steps=data.get("plan_steps"),
            )
        except Exception as e:
            logger.error(f"DEBUG: Failed to parse orchestrator decision: {e}")
            logger.error(f"DEBUG: Raw input was: {json_str[:200]}...")
            
            # Try to extract content using regex (handles truncated JSON)
            import re
            content_match = re.search(r'"content"\s*:\s*"(.*?)(?:"|$)', json_str, re.DOTALL)
            if content_match:
                # Found content field - extract and clean it
                extracted = content_match.group(1)
                # Unescape basic JSON escapes
                extracted = extracted.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
                logger.info(f"DEBUG: Extracted content via regex fallback: {extracted[:100]}...")
                return cls(action=OrchestratorAction.ANSWER, content=extracted)
            
            # Last resort - if it doesn't look like JSON, use as-is
            if not json_str.strip().startswith('{'):
                return cls(action=OrchestratorAction.ANSWER, content=json_str)
            
            # Looks like malformed JSON we can't parse - return error
            logger.error("DEBUG: Could not extract content from malformed JSON")
            return cls(action=OrchestratorAction.ANSWER, content="I had trouble processing that. Could you try again?")

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
        """Resolve orchestration client/model based on effective chat provider.

        Returns:
            tuple: (client, model_name, is_local)
        """
        chat_provider = core_config.get_effective_local_chat_provider()

        if chat_provider == "local_primary":
            try:
                from companion_ai.local_llm import LocalLLM

                local_llm = LocalLLM()
                if local_llm.is_available():
                    return local_llm.get_client(), core_config.get_effective_local_heavy_model(), True
            except Exception as e:
                logger.warning(f"Local-primary chat requested but local backend initialization failed: {e}")

            if not core_config.LOCAL_MODEL_ALLOW_CLOUD_FALLBACK:
                return None, None, False

            logger.warning("Local-primary chat unavailable; falling back to cloud primary model")

        groq_client = self._get_groq_client()
        if groq_client:
            return groq_client, core_config.PRIMARY_MODEL, False

        if chat_provider == "cloud_primary":
            try:
                from companion_ai.local_llm import LocalLLM

                local_llm = LocalLLM()
                if local_llm.is_available():
                    logger.warning("Cloud-primary chat unavailable; falling back to local model")
                    return local_llm.get_client(), core_config.get_effective_local_heavy_model(), True
            except Exception:
                pass

        return None, None, False

    @staticmethod
    def _is_tool_choice_none_error(exc: Exception) -> bool:
        """Detect provider error when model tries tool calls while tools are disabled."""
        msg = str(exc).lower()
        return "tool choice is none" in msg and "called a tool" in msg

    def _chat_completion_with_fallback_model(self, client, model: str, **kwargs):
        """Call chat completions and retry with fallback model on tool-choice mismatch."""
        try:
            response = client.chat.completions.create(model=model, **kwargs)
            return response, model
        except Exception as exc:
            if not self._is_tool_choice_none_error(exc):
                raise

            fallback_model = core_config.MEMORY_PROCESSING_MODEL
            if not fallback_model or fallback_model == model:
                raise

            logger.warning(
                "Model %s attempted a tool call with tool_choice=none semantics; retrying with %s",
                model,
                fallback_model,
            )
            response = client.chat.completions.create(model=fallback_model, **kwargs)
            return response, fallback_model

    @staticmethod
    def _is_smart_home_action(loop_name: str, operation: str) -> bool:
        return loop_name == "tools" and operation in {"light_on", "light_off", "light_dim"}

    @staticmethod
    def _build_smart_home_feedback(operation: str, result: LoopResult) -> Dict[str, Any]:
        data = result.data if isinstance(result.data, dict) else {}
        success = result.status.value == "success"

        if success:
            message = data.get("message") or "Smart home command completed."
        else:
            message = f"Smart home command failed: {result.error or 'Unknown error'}"

        return {
            "domain": "smarthome",
            "operation": operation,
            "status": "success" if success else "error",
            "message": message,
            "prefer_toast": True,
        }

    @staticmethod
    def _is_remote_action(operation: str) -> bool:
        return operation == "remote_action_simulator"

    @staticmethod
    def _build_remote_action_feedback(result: LoopResult) -> Dict[str, Any]:
        envelope = result.data if isinstance(result.data, dict) else result.metadata.get("envelope", {})
        lifecycle = envelope.get("lifecycle") if isinstance(envelope, dict) else []
        status = envelope.get("status") if isinstance(envelope, dict) else None
        reason = envelope.get("reason") if isinstance(envelope, dict) else None
        trace_id = envelope.get("trace_id") if isinstance(envelope, dict) else None

        if status == "completed":
            message = "Remote action completed"
        elif status == "rejected":
            message = f"Remote action rejected: {reason or result.error or 'policy denied'}"
        else:
            message = result.error or "Remote action pending"

        return {
            "domain": "remote_action",
            "operation": "remote_action_simulator",
            "status": "success" if status == "completed" else "error",
            "message": message,
            "prefer_toast": True,
            "trace_id": trace_id,
            "reason": reason,
            "lifecycle": lifecycle if isinstance(lifecycle, list) else [],
            "envelope": envelope if isinstance(envelope, dict) else {},
        }
    
    def _get_capabilities(self) -> str:
        """Get cached loop capabilities string."""
        if not self._capabilities_cache:
            self._capabilities_cache = get_capabilities_summary()
        return self._capabilities_cache
    
    def _build_orchestrator_prompt(self, user_message: str, context: Dict) -> str:
        """Build system prompt for 120B routing decision.
        
        OPTIMIZED FOR GROQ PROMPT CACHING:
        - Static content (routing rules) comes FIRST and is cacheable
        - Dynamic content (user context) comes LAST
        - This maximizes Groq's automatic prefix caching (50% discount on cached tokens)
        """
        # Static content - cacheable by Groq (put first!)
        static_rules = """You are the Companion AI orchestrator. Respond with JSON only.

## Decision Format (JSON only, no markdown)
For direct answers: {"action": "answer", "content": "Your response"}
For tools: {"action": "delegate", "loop": "tools", "task": {"operation": "get_time"}}
For memory save: {"action": "delegate", "loop": "memory", "task": {"operation": "save", "fact": "User's name is Bob"}}
For memory search: {"action": "delegate", "loop": "memory", "task": {"operation": "search", "query": "..."}}
For vision: {"action": "delegate", "loop": "vision", "task": {"operation": "describe"}}
For multi-step tasks: {"action": "plan", "plan_steps": [{"description": "...", "action": "delegate", "params": {"loop": "...", "task": {...}}}, ...]}

## When to use "plan" action
Use "plan" when the user's request requires TWO OR MORE distinct operations that depend on each other.
Examples: "What's the weather like and remind me about my schedule?" → plan with 2 steps.
"Turn on the lights" → single delegate (NOT a plan).
"What time is it?" → single delegate (NOT a plan).
Keep plans SHORT (2-4 steps max). Each step needs a brief description for the user.

## Routing Rules
- "What time?" / "What's today?" → tools (get_time)
- "Calculate X" / "What's 2+2?" → tools (calculate)
- "What's my name?" / "Remember about me" → memory (search)
- Personal recall questions ("what do you remember about me", "what do you know about me", "where do I live", "who am I", "what is my ...") → memory (search)
- "My name is X" / "I am called X" → memory (save) - ALWAYS route to memory!
- "I live in X" / "I'm from X" → memory (save)
- "I work at X" / "My job is X" → memory (save)
- "I prefer X" / "I like X" / "My favorite is X" → memory (save)
- "Save/Remember that X" → memory (save)
- "Look at screen" / "What do you see?" → vision (describe)
- "Go to website" / "Open bookmark" → tools (browser_goto/open_bookmark)
- Direct computer-control commands ("press", "click", "type", "open", "launch", "scroll") → tools (use_computer)
- "Turn on lights" / "Lights on" → tools (light_on, room: "all" or specific room)
- "Turn off lights" / "Lights off" → tools (light_off, room: "all" or specific room)
- "Dim lights to X%" → tools (light_dim, room: "...", level: X)
- "Read this PDF" / "What's in this PDF?" / path ending in .pdf → tools (read_pdf, file_path: "...")
- "Read this file" / "Read document" / .docx / .txt files → tools (read_document, file_path: "...")
- "Find file X" / "Search for file" → tools (find_file, filename: "...")
- "List files in X" / "What files are in..." → tools (list_files, directory: "...")
- "Search my documents for X" / "What do my notes say about X?" / "Find in brain" → tools (brain_search, query: "...")
- Greetings (hi/hello) without personal info → answer directly
- General questions → answer directly

IMPORTANT: For actionable device-control requests, DO NOT answer with capability disclaimers.
Delegate to tools/use_computer first; execution layer will return an honest error if unavailable.

EXCEPTION: If the message contains "[Visual context" then DO NOT delegate to vision. The image was pre-analyzed. Respond based on the context:
- If they ask you to SOLVE something (math, puzzle) → ATTEMPT to solve it with available info. Don't ask for clarification - try your best!
- If they ask "what's in this?" → describe naturally
- If they ask for specific info → find and share it
- DON'T just rephrase the analysis - use it to answer their question

IMPORTANT: When user shares ANY personal info (name, location, job, preferences), ALWAYS route to memory loop with save operation!"""

        # Dynamic content - varies per request (put last)
        recent_context = context.get("recent_conversation", "")
        # Limit context to reduce tokens
        if len(recent_context) > 500:
            recent_context = recent_context[-500:]

        # Persona state — inject evolved traits so routing reflects personality
        persona_fragment = ""
        try:
            from companion_ai.services.persona import get_state as _get_persona
            persona_fragment = _get_persona().prompt_fragment()
        except Exception:
            pass

        dynamic_part = "\n\n## Context\n"
        if persona_fragment:
            dynamic_part += persona_fragment + "\n\n"
        dynamic_part += recent_context if recent_context else "No prior context."
        
        return static_rules + dynamic_part

    @staticmethod
    def _is_explanatory_computer_question(msg: str) -> bool:
        low = (msg or '').strip().lower()
        return low.startswith('how ') or low.startswith('what ') or low.startswith('why ') or low.startswith('can you explain')

    @classmethod
    def _derive_use_computer_task(cls, user_message: str) -> Optional[Dict[str, Any]]:
        """Derive a concrete tools-loop task for imperative computer-control requests."""
        msg = (user_message or '').strip()
        low = msg.lower()
        if not msg or cls._is_explanatory_computer_question(low):
            return None

        def _clean_text(value: str) -> str:
            cleaned = (value or '').strip().strip('"\'')
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            return cleaned.rstrip('.,;')

        def _derive_from_text(text: str) -> Optional[Dict[str, Any]]:
            segment = (text or '').strip()
            if not segment:
                return None

            low_segment = segment.lower()
            candidates: List[Tuple[int, Dict[str, Any]]] = []

            def _add_task(index: int, action: str, text_value: Optional[str] = None, max_len: int = 240) -> None:
                task: Dict[str, Any] = {'operation': 'use_computer', 'action': action}
                if text_value is not None:
                    cleaned = _clean_text(text_value)
                    if not cleaned:
                        return
                    task['text'] = cleaned[:max_len]
                candidates.append((index, task))

            open_tab_match = re.search(r'\bopen\s+(?:another|new)\s+terminal tab\b', low_segment)
            if open_tab_match:
                _add_task(open_tab_match.start(), 'press', 'ctrl+shift+t')

            close_tab_match = re.search(r'\bclose\s+(?:the\s+)?(?:current|this)?\s*tab\b', low_segment)
            if close_tab_match:
                _add_task(close_tab_match.start(), 'press', 'ctrl+shift+w')

            for press_match in re.finditer(r'\bpress\s+([a-z0-9+\-]+)\b', low_segment):
                key = press_match.group(1)
                key = 'Enter' if key == 'enter' else key
                _add_task(press_match.start(), 'press', key)

            for shortcut_match in re.finditer(r'\b((?:ctrl|alt|shift|cmd|win)(?:\+[a-z0-9]+)+)\b', low_segment):
                _add_task(shortcut_match.start(), 'press', shortcut_match.group(1))

            for type_match in re.finditer(r'\btype(?:\s+exactly)?(?:\s+this)?(?:\s+text)?\s*:\s*([^\n\r]+)', segment, flags=re.IGNORECASE):
                _add_task(type_match.start(), 'type', type_match.group(1))

            for type_match in re.finditer(r'\btype\s+([^\n\r]+)', segment, flags=re.IGNORECASE):
                _add_task(type_match.start(), 'type', type_match.group(1))

            for click_match in re.finditer(r'\bclick\s+([^\n\r]+)', segment, flags=re.IGNORECASE):
                _add_task(click_match.start(), 'click', click_match.group(1))

            scroll_up_index = low_segment.find('scroll up')
            if scroll_up_index >= 0:
                _add_task(scroll_up_index, 'scroll_up')

            scroll_down_index = low_segment.find('scroll down')
            if scroll_down_index >= 0:
                _add_task(scroll_down_index, 'scroll_down')

            for launch_match in re.finditer(r'\b(?:open|launch)\s+([^\n\r]+)', segment, flags=re.IGNORECASE):
                launch_target = _clean_text(launch_match.group(1))
                if not launch_target:
                    continue
                # If a shortcut is explicitly present, prefer pressing that shortcut.
                if re.search(r'\b(?:ctrl|alt|shift|cmd|win)\+', launch_target.lower()):
                    continue
                _add_task(launch_match.start(), 'launch', launch_target, max_len=120)

            if not candidates:
                return None

            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

        numbered_steps = [
            m.group(1).strip()
            for m in re.finditer(r'(?m)^\s*\d+[\)\].:-]?\s*(.+)$', msg)
            if m.group(1).strip()
        ]
        if len(numbered_steps) >= 2:
            for step in numbered_steps:
                task = _derive_from_text(step)
                if task:
                    return task

        task = _derive_from_text(msg)
        if task:
            return task

        if any(k in low for k in ['use computer', 'control my computer', 'computer control']):
            return {'operation': 'use_computer', 'action': 'press', 'text': 'Enter'}

        return None

    @staticmethod
    def _derive_memory_search_task(user_message: str) -> Optional[Dict[str, Any]]:
        """Detect personal-recall intent and coerce to memory search when needed."""
        msg = (user_message or '').strip()
        if not msg:
            return None

        low = msg.lower()

        # Common non-recall phrasing where "remember" is instructional, not autobiographical.
        if low.startswith("remember to ") or low.startswith("remember this "):
            return None

        recall_cues = [
            "what do you remember",
            "do you remember",
            "what do you know about me",
            "what do you know about",
            "tell me about me",
            "what's my",
            "what is my",
            "who am i",
            "where do i live",
            "did i tell you",
            "about me",
            "my preferences",
        ]

        personal_refs = [" me", " my ", " i ", "i'", "i "]

        cue_match = any(cue in low for cue in recall_cues)
        personal_match = any(ref in f" {low} " for ref in personal_refs)

        if cue_match and personal_match:
            return {"operation": "search", "query": msg}

        # Fallback: memory-intent questions that include explicit "my <fact>".
        if "?" in low and ("remember" in low or "know" in low) and " my " in f" {low} ":
            return {"operation": "search", "query": msg}

        return None
    
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
        trace_id = str(context.get("trace_id") or "").strip()
        
        try:
            # Step 1: Get 120B decision
            decision = await self._get_decision(user_message, context)
            
            # Step 2: Execute decision
            response, metadata = await self._execute_decision(decision, user_message, context)

            metadata = metadata or {}
            if trace_id:
                metadata.setdefault("trace_id", trace_id)

            # Step 3: Extract structured facts from the completed turn when safe.
            extraction_meta = await self._maybe_extract_turn_facts(
                decision,
                user_message,
                response,
                metadata,
                context,
            )
            if extraction_meta:
                metadata.update(extraction_meta)
            
            # Step 4: Handle explicit memory saving (AFTER response is generated)
            if decision.save_facts:
                await self._save_facts(decision.save_facts, context)
            
            return response, metadata
            
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            fallback_meta = {"error": True}
            if trace_id:
                fallback_meta["trace_id"] = trace_id
            return f"I encountered an error: {str(e)}", fallback_meta
    
    async def _get_decision(self, user_message: str, context: Dict) -> OrchestratorDecision:
        """Get routing decision from local model (or Groq fallback)."""
        import time
        start_time = time.time()
        
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
                max_tokens=300   # Routing JSON is ~100 tokens; no need for 1000
            )
            
            raw_response = response.choices[0].message.content.strip()
            duration_ms = int((time.time() - start_time) * 1000)
            
            # DEBUG: Log the raw response from 120B
            logger.info(f"DEBUG: 120B raw response:\n{raw_response[:500]}...")
            
            # Log tokens with step tracking
            from companion_ai.llm_interface import log_tokens_step
            log_tokens_step(
                step_name="orchestrator",
                model=model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                duration_ms=duration_ms
            )
            
            # Parse decision
            decision = OrchestratorDecision.from_json(raw_response)
            
            # DEBUG: Log the parsed decision
            logger.info(f"DEBUG: Parsed decision: action={decision.action}, loop={decision.loop}, has_content={decision.content is not None}")
            
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
            forced_task = self._derive_use_computer_task(user_message)
            if forced_task:
                logger.info("Coercing actionable computer-control request to tools loop")
                forced_decision = OrchestratorDecision(
                    action=OrchestratorAction.DELEGATE,
                    loop='tools',
                    task=forced_task,
                )
                return await self._handle_delegation(forced_decision, user_message, context)

            forced_memory_task = self._derive_memory_search_task(user_message)
            if forced_memory_task:
                logger.info("Coercing personal-recall request to memory search loop")
                forced_decision = OrchestratorDecision(
                    action=OrchestratorAction.DELEGATE,
                    loop='memory',
                    task=forced_memory_task,
                )
                return await self._handle_delegation(forced_decision, user_message, context)

            if decision.content:
                return decision.content, {"source": "120b_direct"}
            else:
                # Need to generate response (fallback path)
                return await self._generate_direct_response(user_message, context)
        
        elif decision.action == OrchestratorAction.DELEGATE:
            return await self._handle_delegation(decision, user_message, context)
        
        elif decision.action == OrchestratorAction.PLAN:
            return await self._handle_plan(decision, user_message, context)
        
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
        import time
        
        loop_name = decision.loop
        task = dict(decision.task or {})
        if loop_name == "tools" and user_message:
            task.setdefault("user_request", user_message)
        trace_id = str(context.get("trace_id") or "").strip()
        if trace_id:
            task.setdefault("trace_id", trace_id)
        mem0_user_id = context.get("mem0_user_id")
        if mem0_user_id and loop_name == "memory":
            task.setdefault("user_id", mem0_user_id)
        
        # DEBUG: Log delegation attempt
        logger.info(f"DEBUG: Delegating to loop '{loop_name}' with task: {task}")
        
        loop = get_loop(loop_name)
        if not loop:
            logger.error(f"DEBUG: Loop not found: {loop_name}")
            return await self._generate_direct_response(user_message, context)
        
        logger.info(f"DEBUG: Got loop instance: {loop}")
        
        try:
            # Execute loop with timing
            logger.info(f"DEBUG: Executing loop.execute({task})")
            loop_start = time.time()
            result = await loop.execute(task)
            if trace_id and isinstance(result.metadata, dict):
                result.metadata.setdefault("trace_id", trace_id)
            loop_duration_ms = int((time.time() - loop_start) * 1000)

            loop_provider = result.metadata.get("provider") if result and getattr(result, "metadata", None) else None
            loop_model = result.metadata.get("model") if result and getattr(result, "metadata", None) else None
            if loop_name == "browser":
                step_model = "browser_agent"
            elif loop_provider and loop_model:
                step_model = f"{loop_provider}:{loop_model}"
            elif loop_provider:
                step_model = loop_provider
            else:
                step_model = "local"
            
            # Log loop execution as a step (no tokens, but has timing)
            from companion_ai.llm_interface import log_tokens_step
            log_tokens_step(
                step_name=f"loop_{loop_name}",
                model=step_model,
                input_tokens=0,
                output_tokens=0,
                duration_ms=loop_duration_ms
            )

            operation = result.metadata.get("operation") if isinstance(result.metadata, dict) else ""
            metadata_payload = {
                "source": f"loop_{loop_name}",
                "loop_result": result.to_dict()
            }
            if trace_id:
                metadata_payload["trace_id"] = trace_id

            if self._is_smart_home_action(loop_name, operation):
                metadata_payload["action_feedback"] = self._build_smart_home_feedback(operation, result)
            elif self._is_remote_action(operation):
                metadata_payload["action_feedback"] = self._build_remote_action_feedback(result)
            
            if result.status.value == "error":
                logger.error(f"Loop {loop_name} failed: {result.error}")
                if self._is_smart_home_action(loop_name, operation):
                    return (
                        f"I couldn't complete that lighting command: {result.error}",
                        metadata_payload,
                    )
                if self._is_remote_action(operation):
                    reason = ""
                    feedback = metadata_payload.get("action_feedback") if isinstance(metadata_payload, dict) else {}
                    if isinstance(feedback, dict):
                        reason = str(feedback.get("reason") or "").strip()
                    extra = f" (reason: {reason})" if reason else ""
                    return (
                        f"I couldn't complete that remote action{extra}.",
                        metadata_payload,
                    )
                return await self._generate_direct_response(user_message, context)
            
            # Synthesize response with loop result
            response = await self._synthesize_response(
                user_message, 
                loop_name, 
                result.data, 
                context
            )

            return response, metadata_payload
            
        except Exception as e:
            logger.error(f"Loop execution failed: {e}")
            return await self._generate_direct_response(user_message, context)
    
    async def _handle_plan(
        self,
        decision: OrchestratorDecision,
        user_message: str,
        context: Dict
    ) -> Tuple[str, Dict]:
        """Execute a multi-step plan with progress tracking."""
        from companion_ai.services.task_planner import (
            TaskPlan, PlanStep, StepStatus,
            register_plan, update_step_status, complete_plan,
        )

        steps_data = decision.plan_steps or []
        if not steps_data:
            # Fallback — no steps defined, answer directly
            return await self._generate_direct_response(user_message, context)

        # Build plan model
        plan_steps = []
        for i, raw in enumerate(steps_data):
            plan_steps.append(PlanStep(
                id=f"step_{i+1}",
                description=raw.get("description", f"Step {i+1}"),
                action=raw.get("action", "delegate"),
                params=raw.get("params", {}),
            ))

        plan = TaskPlan(
            id=str(__import__("uuid").uuid4())[:8],
            goal=user_message,
            steps=plan_steps,
        )
        register_plan(plan)  # Emits plan.created SSE event
        logger.info(f"Plan {plan.id} created with {len(plan.steps)} steps")

        # Execute steps sequentially, accumulating context
        step_results = []
        accumulated_context = dict(context)

        for step in plan.steps:
            update_step_status(plan.id, step.id, StepStatus.RUNNING)
            try:
                # Build a sub-decision from the step params
                params = step.params or {}
                sub_decision = OrchestratorDecision(
                    action=OrchestratorAction(step.action),
                    loop=params.get("loop"),
                    task=params.get("task"),
                )
                result_text, result_meta = await self._execute_decision(
                    sub_decision, user_message, accumulated_context
                )
                step.result = result_text
                step_results.append({"step": step.description, "result": result_text})
                # Feed result into accumulated context for next step
                accumulated_context["plan_context"] = accumulated_context.get("plan_context", "") + \
                    f"\n[{step.description}]: {result_text}"
                update_step_status(plan.id, step.id, StepStatus.COMPLETED, result=result_text)
            except Exception as e:
                logger.error(f"Plan step {step.id} failed: {e}")
                update_step_status(plan.id, step.id, StepStatus.FAILED, error=str(e))
                step_results.append({"step": step.description, "error": str(e)})

        # Synthesize a final answer from all step results
        synthesis_prompt = f"""You are Companion AI. The user asked: "{user_message}"

You executed a multi-step plan. Here are the results of each step:
{json.dumps(step_results, indent=2)}

Write a natural, conversational response that combines ALL the information.
Do NOT mention "steps" or "plans" — just answer naturally."""

        try:
            from companion_ai.services.persona import get_state as _get_persona
            pf = _get_persona().prompt_fragment()
            if pf:
                synthesis_prompt += f"\n\n{pf}"
        except Exception:
            pass

        client, model, is_local = self._get_client_and_model()
        if client:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": synthesis_prompt}],
                    temperature=0.7,
                    max_tokens=800,
                )
                final_text = resp.choices[0].message.content
            except Exception as e:
                logger.error(f"Plan synthesis failed: {e}")
                final_text = "\n".join(
                    f"• {r['step']}: {r.get('result', r.get('error', '?'))}"
                    for r in step_results
                )
        else:
            final_text = "\n".join(
                f"• {r['step']}: {r.get('result', r.get('error', '?'))}"
                for r in step_results
            )

        complete_plan(plan.id, summary=final_text)
        metadata = {
            "source": "plan",
            "plan_id": plan.id,
            "steps_completed": sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED),
            "steps_total": len(plan.steps),
        }
        trace_id = str(context.get("trace_id") or "").strip()
        if trace_id:
            metadata["trace_id"] = trace_id
        return final_text, metadata

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
        """Quick memory search via unified knowledge recall."""
        try:
            from companion_ai.memory.knowledge import recall
            results = recall(
                user_message,
                limit=8,
                user_id=context.get("mem0_user_id"),
            )
            data = {
                "memories": [{"content": r["text"], "source": r["source"]} for r in results],
                "count": len(results),
                "query": user_message,
            }
        except Exception as e:
            logger.warning(f"knowledge.recall failed, falling back to loop: {e}")
            loop = get_loop("memory")
            if not loop:
                return await self._generate_direct_response(user_message, context)
            result = await loop.execute({"operation": "search", "query": user_message})
            data = result.data

        return await self._synthesize_response(
            user_message,
            "memory",
            data,
            context
        )
    
    async def _generate_direct_response(
        self, 
        user_message: str, 
        context: Dict
    ) -> Tuple[str, Dict]:
        """Generate a direct response without loops (fallback)."""
        trace_id = str(context.get("trace_id") or "").strip()
        client, model, is_local = self._get_client_and_model()
        if not client:
            metadata = {"error": True}
            if trace_id:
                metadata["trace_id"] = trace_id
            return "I'm having connection issues.", metadata
        
        try:
            from companion_ai.core.context_builder import build_system_prompt_with_meta
            
            # Fix: pass user_message and recent_conversation, extract system_prompt from result
            recent_conversation = context.get("recent_conversation", "")
            result = build_system_prompt_with_meta(user_message, recent_conversation)
            system_prompt = result.get("system_prompt", "")
            
            response, _used_model = self._chat_completion_with_fallback_model(
                client,
                model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            source = "local_direct" if is_local else "groq_fallback"
            metadata = {"source": source}
            if trace_id:
                metadata["trace_id"] = trace_id
            return response.choices[0].message.content, metadata
            
        except Exception as e:
            logger.error(f"Direct response failed: {e}")
            metadata = {"error": True}
            if trace_id:
                metadata["trace_id"] = trace_id
            return "Sorry, I'm having trouble responding right now.", metadata
    
    async def _synthesize_response(
        self, 
        user_message: str,
        loop_name: str,
        loop_data: Any,
        context: Dict
    ) -> str:
        """Use local model to synthesize a response from loop output."""
        import time
        start_time = time.time()
        
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

        # Inject persona traits when available
        try:
            from companion_ai.services.persona import get_state as _get_persona
            pf = _get_persona().prompt_fragment()
            if pf:
                synthesis_prompt += f"\n\n{pf}"
        except Exception:
            pass
        
        try:
            response, used_model = self._chat_completion_with_fallback_model(
                client,
                model,
                messages=[
                    {"role": "system", "content": synthesis_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            model_label = "local" if is_local else "groq"
            
            # Log synthesis as a step with tokens and model info
            from companion_ai.llm_interface import log_tokens_step
            log_tokens_step(
                step_name="synthesis",
                model=f"{model_label}:{used_model}",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                duration_ms=duration_ms
            )
            
            logger.info(
                f"Synthesis via {model_label}:{used_model}: "
                f"{response.usage.prompt_tokens if response.usage else 0}+"
                f"{response.usage.completion_tokens if response.usage else 0} tokens in {duration_ms}ms"
            )
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"Based on what I found: {loop_data}"
    
    async def _save_facts(self, facts: List[str], context: Optional[Dict] = None):
        """Save facts via unified knowledge.remember()."""
        if not facts:
            return

        try:
            from companion_ai.memory.knowledge import remember
        except ImportError:
            logger.warning("knowledge module not available for saving facts")
            return

        mem0_user_id = (context or {}).get("mem0_user_id")

        for fact in facts:
            try:
                remember(fact, source="orchestrator", user_id=mem0_user_id)
                logger.info(f"Saved fact via knowledge.remember: {fact}")
            except Exception as e:
                logger.error(f"Failed to save fact '{fact}': {e}")

    async def _maybe_extract_turn_facts(
        self,
        decision: OrchestratorDecision,
        user_message: str,
        response: str,
        metadata: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract and persist structured facts from a completed turn."""
        if not core_config.MEMORY_AUTO_EXTRACT:
            return {}
        if not user_message or not response:
            return {}

        source = (metadata or {}).get("source", "")
        if decision.loop == "memory" or source == "loop_memory":
            return {}

        loop = get_loop("memory")
        if not loop:
            return {}

        combined_text = f"User: {user_message}\nAI: {response}"
        try:
            result = await loop.execute({"operation": "extract", "text": combined_text})
        except Exception as e:
            logger.warning(f"Auto extraction failed before persistence: {e}")
            return {"auto_extraction_error": str(e)}

        if result.status.value == "error":
            return {"auto_extraction_error": result.error or "extract_failed"}

        extracted_facts = (result.data or {}).get("extracted_facts", [])
        if not extracted_facts:
            return {"auto_extracted_facts": 0, "auto_saved_facts": 0, "auto_review_facts": 0}

        persistence_meta = self._store_extracted_facts(extracted_facts, context or {})
        persistence_meta["auto_extracted_facts"] = len(extracted_facts)
        return persistence_meta

    def _store_extracted_facts(self, extracted_facts: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, int]:
        """Persist extracted facts using confidence-gated storage rules."""
        if not extracted_facts:
            return {"auto_saved_facts": 0, "auto_review_facts": 0}

        from companion_ai.memory.knowledge import remember
        from companion_ai.memory.sqlite_backend import queue_pending_profile_fact, upsert_profile_fact

        mem0_user_id = context.get("mem0_user_id")
        auto_save_threshold = getattr(core_config, "FACT_AUTO_APPROVE_THRESHOLD", 0.85)
        review_threshold = getattr(core_config, "FACT_CONFIDENCE_THRESHOLD", 0.5)
        auto_saved = 0
        review_only = 0

        for item in extracted_facts:
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            if not key or not value:
                continue

            confidence = float(item.get("confidence", 0.0) or 0.0)
            evidence = item.get("evidence")
            fact_text = str(item.get("fact") or f"User {key.replace('_', ' ')} is {value}")

            if confidence >= auto_save_threshold:
                upsert_profile_fact(
                    key,
                    value,
                    confidence,
                    source="auto_extract",
                    evidence=evidence,
                    model_conf_label=item.get("conf_label"),
                    justification=item.get("justification"),
                )
                try:
                    remember(
                        fact_text,
                        source="auto_extract",
                        user_id=mem0_user_id,
                        skip_sqlite=True,
                    )
                    auto_saved += 1
                except Exception as e:
                    logger.warning(f"Failed to persist extracted fact to Mem0: {e}")
            else:
                queue_pending_profile_fact(
                    key,
                    value,
                    confidence=max(confidence, min(review_threshold - 0.01, confidence)),
                    source="auto_extract",
                    evidence=evidence,
                    model_conf_label=item.get("conf_label"),
                    justification=item.get("justification"),
                )
                review_only += 1

        return {"auto_saved_facts": auto_saved, "auto_review_facts": review_only}


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
