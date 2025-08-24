"""Minimal tool registry & execution (Phase 0 prototype).

Tools are simple callables returning text. Later phases can add schema & args.
"""
from __future__ import annotations
import math, datetime, re
from typing import Callable, Dict

ToolFn = Callable[[str], str]

_TOOLS: Dict[str, ToolFn] = {}

def tool(name: str):
    def wrap(fn: ToolFn):
        _TOOLS[name] = fn
        return fn
    return wrap

@tool('time')
def tool_time(_: str) -> str:
    return datetime.datetime.now().isoformat(timespec='seconds')

@tool('calc')
def tool_calc(expr: str) -> str:
    try:
        # extremely restricted eval: digits, operators, parentheses, dots, spaces
        if not all(c in '0123456789+-*/(). %' for c in expr):
            return 'Invalid characters'
        return str(eval(expr, {'__builtins__': {'abs': abs, 'round': round, 'pow': pow}, 'math': math}, {}))
    except Exception as e:
        return f'calc error: {e}'

@tool('search')
def tool_search(query: str) -> str:
    """Stub search tool returning keyword echo.
    Future: integrate actual retrieval.
    """
    q = query.strip()
    if not q:
        return 'search: (empty query)'
    terms = [t for t in re.split(r'\W+', q.lower()) if len(t) > 3][:6]
    return f"search_results_stub: keywords={terms}"

def list_tools() -> list[str]:
    return sorted(_TOOLS.keys())

def run_tool(name: str, arg: str) -> str:
    fn = _TOOLS.get(name)
    if not fn:
        return 'unknown tool'
    return fn(arg)

__all__ = ['list_tools', 'run_tool']