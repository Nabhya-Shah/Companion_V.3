"""Compatibility wrapper for legacy token budget imports."""

from companion_ai.services.token_budget import (
    TokenBudget,
    get_token_budget,
    record_tokens,
    get_budget_status,
    should_auto_save,
)

__all__ = [
    "TokenBudget",
    "get_token_budget",
    "record_tokens",
    "get_budget_status",
    "should_auto_save",
]
