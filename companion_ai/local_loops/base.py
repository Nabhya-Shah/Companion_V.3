# companion_ai/local_loops/base.py
"""
Base Loop class - All loops inherit from this.

Design Philosophy:
- Loops are the "hands" - they execute, never persist
- Only 120B (the brain) decides what to save
- Each loop has injectable system prompts
- Loops can have multiple models working together
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LoopStatus(Enum):
    """Status of a loop execution."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"


@dataclass
class LoopResult:
    """Result from a loop execution.
    
    Attributes:
        status: Execution status
        data: The actual result data (varies by loop type)
        error: Error message if status is ERROR
        metadata: Additional info (tokens used, time taken, etc.)
    """
    status: LoopStatus
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }
    
    @classmethod
    def success(cls, data: Any, **metadata) -> "LoopResult":
        """Create a successful result."""
        return cls(status=LoopStatus.SUCCESS, data=data, metadata=metadata)
    
    @classmethod
    def failure(cls, error: str, **metadata) -> "LoopResult":
        """Create a failed result."""
        return cls(status=LoopStatus.ERROR, error=error, metadata=metadata)


class Loop(ABC):
    """Abstract base class for all loops.
    
    Each loop:
    - Has a name and description (for 120B to understand capabilities)
    - Has injectable system prompts for its models
    - Executes tasks and returns structured LoopResult
    - Never persists data (only 120B does that)
    """
    
    # Override in subclasses
    name: str = "base"
    description: str = "Base loop - do not use directly"
    
    # System prompts for models in this loop
    system_prompts: Dict[str, str] = {}
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the loop.
        
        Args:
            config: Optional configuration dict (model endpoints, etc.)
        """
        self.config = config or {}
        self._setup()
    
    def _setup(self) -> None:
        """Override to do any setup (connect to models, etc.)."""
        pass
    
    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a task.
        
        Args:
            task: Task definition from 120B orchestrator
                  Format varies by loop type
                  
        Returns:
            LoopResult with status and data
        """
        raise NotImplementedError
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get loop capabilities for 120B to understand.
        
        Returns dict that 120B uses to decide when to delegate.
        """
        return {
            "name": self.name,
            "description": self.description,
            "supported_operations": self._get_supported_operations()
        }
    
    def _get_supported_operations(self) -> List[str]:
        """Override to list what operations this loop supports."""
        return []
    
    def get_system_prompt(self, role: str = "default") -> str:
        """Get system prompt for a specific role in this loop.
        
        Args:
            role: Which model/role needs the prompt
            
        Returns:
            System prompt string
        """
        return self.system_prompts.get(role, "")
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}'>"
