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
        """Search for relevant memories from all sources.
        
        PRIORITY: Brain files > Mem0
        Brain files are the source of truth. When searching:
        1. Check brain files first
        2. Extract key facts from brain (name, location, job, etc.)
        3. Search Mem0 for additional context
        4. Skip Mem0 results that conflict with brain facts
        """
        if not query:
            return LoopResult.failure("No query provided")
        
        results = []
        query_lower = query.lower()
        brain_facts = {}  # Store brain facts by category for deduplication
        
        try:
            # Source 1: Search brain files FIRST (source of truth)
            from companion_ai.brain_manager import get_brain
            import re
            brain = get_brain()
            
            # Categories to track for deduplication
            fact_patterns = {
                "name": r"name[:\s]+(\w+)",
                "location": r"(live[s]?|based|from)[:\s]+(\w+)",
                "job": r"(work|job|occupation)[:\s]+(.+)",
            }
            
            brain_files = [
                "memories/preferences.md",
                "memories/user_context.md", 
                "memories/personality.md"
            ]
            
            for brain_file in brain_files:
                content = brain.read(brain_file)
                if content:
                    lines = content.split('\n')
                    for line in lines:
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith('<!--'):
                            continue
                        
                        # Extract category facts from brain
                        for category, pattern in fact_patterns.items():
                            if re.search(pattern, line_clean, re.IGNORECASE):
                                brain_facts[category] = line_clean
                        
                        # Check if query matches this line
                        if any(word in line_clean.lower() for word in query_lower.split()):
                            results.append({
                                "source": "brain",
                                "file": brain_file,
                                "content": line_clean,
                                "priority": 1  # Brain has priority
                            })
            
            # Source 2: Search Mem0 for additional context
            try:
                from companion_ai.memory import mem0_backend as memory_v2
                mem0_results = memory_v2.search_memories(query, limit=5)
                
                for mem in mem0_results:
                    mem_text = mem.get("memory", mem.get("text", str(mem)))
                    mem_lower = mem_text.lower()
                    
                    # Check if this Mem0 result conflicts with brain facts
                    is_conflicting = False
                    for category, pattern in fact_patterns.items():
                        if category in brain_facts and re.search(pattern, mem_lower, re.IGNORECASE):
                            # Same category exists in brain - check for conflict
                            if brain_facts[category].lower() not in mem_lower and mem_lower not in brain_facts[category].lower():
                                logger.info(f"🔄 Skipping conflicting Mem0 fact '{mem_text}' - brain has '{brain_facts[category]}'")
                                is_conflicting = True
                                break
                    
                    if not is_conflicting:
                        results.append({
                            "source": "mem0",
                            "content": mem_text,
                            "priority": 2  # Mem0 has lower priority
                        })
            except Exception as e:
                logger.debug(f"Mem0 search skipped: {e}")
            
            # Sort by priority (brain first)
            results.sort(key=lambda x: x.get("priority", 2))
            
            logger.info(f"Memory search for '{query}': found {len(results)} results (brain: {len(brain_facts)} key facts)")
            
            return LoopResult.success(
                data={
                    "memories": results, 
                    "count": len(results),
                    "query": query,
                    "brain_facts": brain_facts  # Include extracted brain facts
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
        """Save a fact to memory - DUAL STORAGE with CONFLICT DETECTION.
        
        CONFLICT DETECTION: Before saving, checks if a similar fact exists.
        If conflict found (e.g., saving "Name is Bob" when "Name is Nabhya" exists),
        returns a clarification message instead of silently saving.
        
        Writes to:
        1. Mem0 (vector database for semantic search)
        2. Brain folder (readable markdown files)
        """
        if not fact:
            return LoopResult.failure("No fact provided")
        
        try:
            from companion_ai.memory import mem0_backend as memory_v2
            from companion_ai.core import config as core_config
            from companion_ai.brain_manager import get_brain
            from datetime import datetime
            import re
            
            # CONFLICT DETECTION: Check for existing similar facts
            fact_lower = fact.lower()
            
            # Define fact categories and their search terms
            conflict_patterns = [
                (r"name is|called|my name", "name"),
                (r"live in|from|based in|location", "location"),
                (r"work at|job is|occupation|employed", "job"),
                (r"favorite|prefer|like", "preference"),
            ]
            
            detected_category = None
            for pattern, category in conflict_patterns:
                if re.search(pattern, fact_lower):
                    detected_category = category
                    break
            
            if detected_category:
                # Search for existing facts in this category
                existing = memory_v2.search_memories(detected_category, user_id=core_config.MEM0_USER_ID, limit=5)
                
                # Also check brain files
                brain = get_brain()
                user_context = brain.read("memories/user_context.md")
                
                for mem in existing:
                    mem_text = mem.get("memory", mem.get("text", ""))
                    mem_lower = mem_text.lower()
                    
                    # Check if this is a conflicting fact (same category, different value)
                    if re.search(pattern, mem_lower):
                        # Found existing fact of same type - check if it's different
                        if mem_text.lower() != fact_lower:
                            logger.info(f"🔄 Conflict detected: existing '{mem_text}' vs new '{fact}'")
                            return LoopResult.success(
                                data={
                                    "conflict": True,
                                    "existing_fact": mem_text,
                                    "new_fact": fact,
                                    "category": detected_category,
                                    "question": f"I have '{mem_text}' saved. Should I update this to '{fact}'?"
                                },
                                operation="save_conflict"
                            )
                
                # Also check brain user_context.md for conflicts
                if user_context:
                    for line in user_context.split("\n"):
                        if re.search(pattern, line.lower()) and fact_lower not in line.lower():
                            logger.info(f"🔄 Brain conflict detected: existing '{line}' vs new '{fact}'")
                            return LoopResult.success(
                                data={
                                    "conflict": True,
                                    "existing_fact": line.strip(),
                                    "new_fact": fact,
                                    "category": detected_category,
                                    "source": "brain",
                                    "question": f"Your profile says '{line.strip()}'. Should I update this to '{fact}'?"
                                },
                                operation="save_conflict"
                            )
            
            # No conflict found - proceed with saving
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
