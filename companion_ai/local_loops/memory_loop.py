# companion_ai/local_loops/memory_loop.py
"""
Memory Loop - Extract and retrieve facts using local model.

Operations:
- search: Find relevant memories for a query
- extract: Extract facts from conversation text
- save: Store a fact (called by 120B after deciding what to save)

Uses a small local text model (e.g., Qwen 3B) for fast fact extraction.
"""

import logging
import re
from typing import Any, Dict, List
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


@register_loop
class MemoryLoop(Loop):
    """Memory extraction and retrieval loop."""
    
    name = "memory"
    description = "Extract facts from text, search memories, and store information"
    
    system_prompts = {
        "extractor": """You are a fact extraction agent. Your job is to identify 
concrete, factual information from conversation text.

Extract ONLY:
- Names, ages, relationships
- Preferences and opinions  
- Important dates and events
- Skills and professions
- Locations and places

Do NOT extract:
- Casual greetings
- Questions without answers
- Vague statements

Return facts as a JSON array of strings.""",

        "searcher": """You are a memory search agent. Given a query, find the most 
relevant memories from the provided list. Return the indices of relevant memories."""
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._model_endpoint = None
    
    def _setup(self) -> None:
        """Connect to local model."""
        # Will be configured when Docker vLLM is ready
        self._model_endpoint = self.config.get("model_endpoint", "http://localhost:8000/v1")
        logger.info(f"MemoryLoop configured with endpoint: {self._model_endpoint}")
    
    def _get_supported_operations(self) -> List[str]:
        return ["search", "extract", "save", "delete"]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a memory task.
        
        Task format:
            {"operation": "search", "query": "user's name"}
            {"operation": "extract", "text": "conversation text..."}
            {"operation": "save", "fact": "User's name is Bob"}
            {"operation": "delete", "query": "fact to forget"}
        """
        operation = task.get("operation")
        user_id = task.get("user_id")
        
        if operation == "search":
            return await self._search(task.get("query", ""), user_id=user_id)
        elif operation == "extract":
            return await self._extract(task.get("text", ""))
        elif operation == "save":
            return await self._save(task.get("fact", ""), user_id=user_id)
        elif operation == "delete":
            return await self._delete(task.get("query", ""))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _search(self, query: str, user_id: str | None = None) -> LoopResult:
        """Search for relevant memories via unified knowledge.recall()."""
        if not query:
            return LoopResult.failure("No query provided")

        try:
            from companion_ai.memory.knowledge import recall
            results = recall(query, limit=10, user_id=user_id)
            memories = [
                {"source": r["source"], "content": r["text"], "priority": 1 if r["source"] == "brain" else 2}
                for r in results
            ]
            logger.info(f"Memory search for '{query}': found {len(memories)} results via knowledge.recall")
            return LoopResult.success(
                data={"memories": memories, "count": len(memories), "query": query},
                operation="search",
            )
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _extract(self, text: str) -> LoopResult:
        """Extract structured facts from text using the memory AI path."""
        if not text:
            return LoopResult.failure("No text provided")

        # Strip image-analysis context from memory extraction input.
        text = re.sub(r'\[Visual context from user\'s uploaded file:.*?\]', '', text, flags=re.DOTALL)

        try:
            logger.info(f"MemoryLoop._extract called with {len(text)} chars")

            from companion_ai.memory.ai_processor import extract_profile_facts_from_text

            extracted = extract_profile_facts_from_text(text)
            extracted_facts = []
            for key, item in extracted.items():
                extracted_facts.append({
                    "key": key,
                    "value": item.get("value", ""),
                    "confidence": item.get("confidence", 0.0),
                    "conf_label": item.get("conf_label"),
                    "evidence": item.get("evidence"),
                    "justification": item.get("justification"),
                    "fact": item.get("fact"),
                })

            extracted_facts.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)

            return LoopResult.success(
                data={
                    "extracted_facts": extracted_facts,
                    "count": len(extracted_facts),
                },
                operation="extract",
                text_length=len(text)
            )
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _save(self, fact: str, user_id: str | None = None) -> LoopResult:
        """Save a fact via unified knowledge.remember().

        Also writes to brain folder for human-readable backup.
        """
        if not fact:
            return LoopResult.failure("No fact provided")

        # EXCLUDE: Skip saving image analysis context
        if "Visual context from user" in fact or "image shows" in fact.lower():
            logger.info("Skipping image context from memory storage")
            return LoopResult.success(
                data={"skipped": True, "reason": "Image context excluded from memory"},
                operation="save",
            )

        try:
            from companion_ai.memory.knowledge import remember
            from companion_ai.brain_manager import get_brain
            from datetime import datetime

            result = remember(fact, source="loop_memory", user_id=user_id)

            # Also append to brain folder for human-readable log
            brain = get_brain()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            brain.write("memories/facts.md", f"- [{timestamp}] {fact}\n", append=True)

            runtime = {}
            mem0_result = result.get("mem0") if isinstance(result, dict) else None
            if isinstance(mem0_result, dict):
                runtime = mem0_result.get("runtime") or {}

            logger.info(f"Saved fact via knowledge.remember: {fact[:50]}...")
            return LoopResult.success(
                data={"saved": True, "fact": fact, "result": result, "brain": "memories/facts.md"},
                operation="save",
                provider=runtime.get("provider", "unknown"),
                model=runtime.get("model", "unknown"),
            )
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _delete(self, query: str) -> LoopResult:
        """Delete/forget a memory matching the query.
        
        Searches for matching memories and removes them.
        """
        if not query:
            return LoopResult.failure("No query provided for deletion")
        
        try:
            from companion_ai.memory import mem0_backend as mem0
            from companion_ai.core import config as core_config
            
            # First search for matching memories
            results = mem0.search_memories(query, user_id=core_config.MEM0_USER_ID, limit=3)
            
            if not results:
                return LoopResult.success(
                    data={"deleted": 0, "message": f"No memories found matching: {query}"},
                    operation="delete"
                )
            
            # Delete matching memories
            deleted_count = 0
            for mem in results:
                mem_id = mem.get("id")
                if mem_id:
                    mem0.delete_memory(mem_id)
                    deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} memories matching: {query}")
            
            return LoopResult.success(
                data={"deleted": deleted_count, "query": query},
                operation="delete"
            )
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return LoopResult.failure(str(e))
