"""
Token Budget Manager - Track and warn about Groq token usage.

Provides:
- Daily token tracking per model
- Warning at 80% usage
- Auto brain-write trigger at 90% or when next message would exceed limit
"""

import os
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Groq Free Tier Limits (TPD = Tokens Per Day)
# Source: Groq Console / API docs
GROQ_FREE_LIMITS = {
    # Primary models
    "openai/gpt-oss-120b": 6_000_000,      # 6M tokens/day
    "llama-3.1-8b-instant": 6_000_000,      # 6M tokens/day
    # Vision models  
    "llama-4-maverick-17b-128e-instruct": 500_000,  # 500K tokens/day
    # Fallbacks
    "default": 500_000,  # Conservative default
}

# Thresholds
WARNING_THRESHOLD = 0.80   # Yellow warning at 80%
AUTOWRITE_THRESHOLD = 0.90  # Auto brain-write at 90%

# Persistence file
DATA_DIR = Path(__file__).parent.parent / "data"
BUDGET_FILE = DATA_DIR / "token_budget.json"


class TokenBudget:
    """Tracks daily token usage and triggers warnings/auto-saves."""
    
    def __init__(self):
        self._usage = {}  # {model: {date: tokens}}
        self._load()
    
    def _load(self):
        """Load persisted usage from file."""
        try:
            if BUDGET_FILE.exists():
                with open(BUDGET_FILE, "r") as f:
                    data = json.load(f)
                    self._usage = data.get("usage", {})
        except Exception as e:
            logger.error(f"Failed to load token budget: {e}")
            self._usage = {}
    
    def _save(self):
        """Persist usage to file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(BUDGET_FILE, "w") as f:
                json.dump({"usage": self._usage, "updated": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.error(f"Failed to save token budget: {e}")
    
    def record_usage(self, model: str, tokens: int):
        """Record token usage for a model."""
        today = str(date.today())
        
        if model not in self._usage:
            self._usage[model] = {}
        if today not in self._usage[model]:
            self._usage[model][today] = 0
        
        self._usage[model][today] += tokens
        self._save()
        
        # Log warning if approaching limit
        status = self.get_status(model)
        if status["percent"] >= AUTOWRITE_THRESHOLD * 100:
            logger.warning(f"Token budget CRITICAL: {model} at {status['percent']:.1f}%")
        elif status["percent"] >= WARNING_THRESHOLD * 100:
            logger.warning(f"Token budget WARNING: {model} at {status['percent']:.1f}%")
    
    def get_limit(self, model: str) -> int:
        """Get daily limit for a model."""
        # Check for exact match first
        if model in GROQ_FREE_LIMITS:
            return GROQ_FREE_LIMITS[model]
        
        # Check for partial match (model families)
        for key, limit in GROQ_FREE_LIMITS.items():
            if key in model or model in key:
                return limit
        
        return GROQ_FREE_LIMITS["default"]
    
    def get_usage_today(self, model: str) -> int:
        """Get today's usage for a model."""
        today = str(date.today())
        return self._usage.get(model, {}).get(today, 0)
    
    def get_status(self, model: str = None) -> dict:
        """
        Get budget status for a model (or aggregate).
        
        Returns:
            {
                "used": int,
                "limit": int,
                "remaining": int,
                "percent": float,
                "warning": bool,
                "critical": bool,
                "model": str
            }
        """
        if model:
            used = self.get_usage_today(model)
            limit = self.get_limit(model)
        else:
            # Aggregate across most-used model
            today = str(date.today())
            all_usage = []
            for m, dates in self._usage.items():
                if today in dates:
                    all_usage.append((m, dates[today], self.get_limit(m)))
            
            if all_usage:
                # Return status of highest-percentage model
                all_usage.sort(key=lambda x: x[1] / x[2], reverse=True)
                model, used, limit = all_usage[0]
            else:
                model = "default"
                used = 0
                limit = GROQ_FREE_LIMITS["default"]
        
        remaining = max(0, limit - used)
        percent = (used / limit * 100) if limit > 0 else 0
        
        return {
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "percent": round(percent, 1),
            "warning": percent >= WARNING_THRESHOLD * 100,
            "critical": percent >= AUTOWRITE_THRESHOLD * 100,
            "model": model,
        }
    
    def would_exceed(self, model: str, estimated_tokens: int) -> bool:
        """Check if the next message would exceed the limit."""
        used = self.get_usage_today(model)
        limit = self.get_limit(model)
        return (used + estimated_tokens) >= limit
    
    def should_auto_save(self, model: str = None, next_tokens: int = 0) -> bool:
        """
        Determine if we should trigger auto brain-write.
        
        Triggers at:
        - 90% usage
        - OR if next message would exceed limit
        """
        status = self.get_status(model)
        
        if status["critical"]:
            return True
        
        if next_tokens > 0 and model:
            if self.would_exceed(model, next_tokens):
                logger.warning(f"Next message ({next_tokens} tokens) would exceed limit for {model}")
                return True
        
        return False
    
    def reset_today(self, model: str = None):
        """Reset today's usage (mainly for testing)."""
        today = str(date.today())
        if model:
            if model in self._usage and today in self._usage[model]:
                self._usage[model][today] = 0
        else:
            for m in self._usage:
                if today in self._usage[m]:
                    self._usage[m][today] = 0
        self._save()


# Singleton
_budget: Optional[TokenBudget] = None


def get_token_budget() -> TokenBudget:
    """Get the global TokenBudget instance."""
    global _budget
    if _budget is None:
        _budget = TokenBudget()
    return _budget


# Convenience functions
def record_tokens(model: str, tokens: int):
    """Record token usage."""
    get_token_budget().record_usage(model, tokens)


def get_budget_status(model: str = None) -> dict:
    """Get current budget status."""
    return get_token_budget().get_status(model)


def should_auto_save(model: str = None, next_tokens: int = 0) -> bool:
    """Check if auto brain-write should trigger."""
    return get_token_budget().should_auto_save(model, next_tokens)
