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
        return ["search", "extract", "save"]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a memory task.
        
        Task format:
            {"operation": "search", "query": "user's name"}
            {"operation": "extract", "text": "conversation text..."}
            {"operation": "save", "fact": "User's name is Bob"}
        """
        operation = task.get("operation")
        
        if operation == "search":
            return await self._search(task.get("query", ""))
        elif operation == "extract":
            return await self._extract(task.get("text", ""))
        elif operation == "save":
            return await self._save(task.get("fact", ""))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _search(self, query: str) -> LoopResult:
        """Search for relevant memories."""
        if not query:
            return LoopResult.failure("No query provided")
        
        try:
            # Use existing Mem0 search
            from companion_ai import memory_v2
            
            memories = memory_v2.search_memories(query, limit=10)
            
            return LoopResult.success(
                data={"memories": memories, "count": len(memories)},
                operation="search",
                query=query
            )
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _extract(self, text: str) -> LoopResult:
        """Extract facts from text using local model.
        
        TODO: Connect to Docker vLLM when ready.
        For now, returns empty to avoid breaking things.
        """
        if not text:
            return LoopResult.failure("No text provided")
        
        try:
            # TODO: Call local vLLM with extractor prompt
            # For now, placeholder that returns empty
            logger.info(f"MemoryLoop._extract called with {len(text)} chars")
            
            # Placeholder - will use local model
            extracted_facts = []
            
            return LoopResult.success(
                data={"extracted_facts": extracted_facts},
                operation="extract",
                text_length=len(text)
            )
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _save(self, fact: str) -> LoopResult:
        """Save a fact to memory.
        
        Called by 120B after it decides something is worth saving.
        """
        if not fact:
            return LoopResult.failure("No fact provided")
        
        try:
            from companion_ai import memory_v2
            from companion_ai.core import config as core_config
            
            # Add to Mem0
            result = memory_v2.add_memory(
                text=fact,
                user_id=core_config.MEM0_USER_ID,
                metadata={"source": "120b_decision"}
            )
            
            logger.info(f"Saved fact via MemoryLoop: {fact[:50]}...")
            
            return LoopResult.success(
                data={"saved": True, "fact": fact},
                operation="save"
            )
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            return LoopResult.failure(str(e))
