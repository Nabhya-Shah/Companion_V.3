"""Minimal tool registry & execution (Phase 0 prototype).

Tools are simple callables returning text. Later phases can add schema & args.
"""
from __future__ import annotations
import math, datetime, re, os, textwrap, json
from typing import Callable, Dict
from companion_ai import memory as mem
try:
    import requests  # for optional web snippet
except ImportError:  # graceful degrade
    requests = None
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
    """Memory-first search with optional lightweight web enrichment.

    Query format (simple):
      <free text>
    To disable web fallback explicitly append: --no-web
    """
    q = (query or '').strip()
    if not q:
        return 'SEARCH_RESULTS (empty query)'
    use_web = True
    if '--no-web' in q:
        q = q.replace('--no-web', '').strip()
        use_web = False

    # Memory search
    mem_hits = mem.search_memory(q, limit=8)
    if not mem_hits and len(q.split()) == 1:
        # broaden by not requiring >1 char tokens (already simple)
        pass

    lines = [f"SEARCH_RESULTS (query='{q}', memory_hits={len(mem_hits)})"]
    for i, hit in enumerate(mem_hits, 1):
        snippet = hit['text']
        if len(snippet) > 140:
            snippet = snippet[:137] + '...'
        lines.append(f"{i}. [{hit['type']}] score={hit['score']:.2f} | {snippet}")

    # Optional small web snippet: simple Wikipedia-style summary fallback
    if use_web and requests and len(mem_hits) < 3:
        try:
            # naive endpoint (could swap later); using duckduckgo instant answer style
            resp = requests.get(
                'https://api.duckduckgo.com/',
                params={'q': q, 'format': 'json', 'no_html': 1, 'skip_disambig': 1}, timeout=3.5
            )
            if resp.ok:
                data = resp.json()
                abstract = data.get('AbstractText') or ''
                if abstract:
                    abstract = re.sub(r'\s+', ' ', abstract).strip()
                    if abstract:
                        short = abstract[:220] + ('...' if len(abstract) > 220 else '')
                        lines.append(f"WEB: {short}")
        except Exception:
            lines.append("WEB: (unavailable)")
    return '\n'.join(lines)

def list_tools() -> list[str]:
    return sorted(_TOOLS.keys())

def run_tool(name: str, arg: str) -> str:
    fn = _TOOLS.get(name)
    if not fn:
        return 'unknown tool'
    return fn(arg)

@tool('memory_insight')
def tool_memory_insight(_: str) -> str:
    """Generate a quick synthetic insight over last few summaries+insights (read-only)."""
    try:
        # dynamic import inside try to avoid circular dependency during module load
        from companion_ai.llm_interface import generate_groq_response  # type: ignore
        summaries = mem.get_latest_summary(3)
        insights = mem.get_latest_insights(3)
        profile = mem.get_all_profile_facts()
        prompt = (
            "You are generating a SINGLE concise actionable observation about the user based on provided data.\n"
            "Focus on a helpful pattern or preference. Avoid repetition. Max 2 sentences.\n\n"
            f"Profile facts: {profile}\nRecent summaries: {[s['summary_text'] for s in summaries]}\n"
            f"Existing insights: {[i['insight_text'] for i in insights]}\n\nObservation:"
        )
        text = generate_groq_response(prompt) or '(no insight)'
        return text.strip()
    except Exception as e:
        return f"memory_insight error: {e}"

__all__ = ['list_tools', 'run_tool']