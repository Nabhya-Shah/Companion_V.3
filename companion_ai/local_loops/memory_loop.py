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
        
        if operation == "search":
            return await self._search(task.get("query", ""))
        elif operation == "extract":
            return await self._extract(task.get("text", ""))
        elif operation == "save":
            return await self._save(task.get("fact", ""))
        elif operation == "delete":
            return await self._delete(task.get("query", ""))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _search(self, query: str) -> LoopResult:
        """Search for relevant memories from all sources."""
        if not query:
            return LoopResult.failure("No query provided")
        
        results = []
        query_lower = query.lower()
        
        try:
            # Source 1: Search brain files (preferences, user context)
            from companion_ai.brain_manager import get_brain
            brain = get_brain()
            
            # Check key brain files
            brain_files = [
                "memories/preferences.md",
                "memories/user_context.md", 
                "memories/personality.md"
            ]
            
            for brain_file in brain_files:
                content = brain.read(brain_file)
                if content:
                    # Simple keyword matching
                    lines = content.split('\n')
                    for line in lines:
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith('<!--'):
                            continue
                        # Check if query matches this line
                        if any(word in line_clean.lower() for word in query_lower.split()):
                            results.append({
                                "source": "brain",
                                "file": brain_file,
                                "content": line_clean
                            })
            
            # Source 2: Search Mem0 if available
            try:
                from companion_ai.memory import mem0_backend as memory_v2
                mem0_results = memory_v2.search_memories(query, limit=5)
                for mem in mem0_results:
                    results.append({
                        "source": "mem0",
                        "content": mem.get("text", str(mem))
                    })
            except Exception as e:
                logger.debug(f"Mem0 search skipped: {e}")
            
            logger.info(f"Memory search for '{query}': found {len(results)} results")
            
            return LoopResult.success(
                data={
                    "memories": results, 
                    "count": len(results),
                    "query": query
                },
                operation="search"
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
        """Save a fact to memory - DUAL STORAGE.
        
        Writes to:
        1. Mem0 (vector database for semantic search)
        2. Brain folder (readable markdown files)
        
        Called by 120B after it decides something is worth saving.
        """
        if not fact:
            return LoopResult.failure("No fact provided")
        
        try:
            from companion_ai.memory import mem0_backend as memory_v2
            from companion_ai.core import config as core_config
            from companion_ai.brain_manager import get_brain
            from datetime import datetime
            
            # 1. Add to Mem0 (for vector search)
            messages = [{"role": "user", "content": fact}]
            mem0_result = memory_v2.add_memory(
                messages=messages,
                user_id=core_config.MEM0_USER_ID,
                metadata={"source": "brain_save"}
            )
            
            # 2. Add to Brain folder (for readable storage)
            brain = get_brain()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Append to memories/facts.md (create if needed)
            fact_entry = f"- [{timestamp}] {fact}\n"
            brain.write("memories/facts.md", fact_entry, append=True)
            
            logger.info(f"Saved fact to BOTH Mem0 and brain: {fact[:50]}...")
            
            return LoopResult.success(
                data={"saved": True, "fact": fact, "mem0": mem0_result, "brain": "memories/facts.md"},
                operation="save"
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
            from companion_ai.memory import mem0_backend as memory_v2
            from companion_ai.core import config as core_config
            
            # First search for matching memories
            results = memory_v2.search_memories(query, user_id=core_config.MEM0_USER_ID, limit=3)
            
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
                    memory_v2.delete_memory(mem_id)
                    deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} memories matching: {query}")
            
            return LoopResult.success(
                data={"deleted": deleted_count, "query": query},
                operation="delete"
            )
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return LoopResult.failure(str(e))
