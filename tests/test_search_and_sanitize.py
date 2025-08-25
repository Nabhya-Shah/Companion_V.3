import re
from companion_ai.tools import run_tool
from companion_ai import memory as mem
from companion_ai.llm_interface import sanitize_output

def test_search_memory_empty():
    out = run_tool('search', 'nonexistentgibberishterm --no-web')
    assert 'memory_hits=0' in out

def test_search_memory_basic(monkeypatch):
    # Seed a fact
    mem.upsert_profile_fact('favorite_game', 'Elden Ring')
    out = run_tool('search', 'Elden Ring --no-web')
    assert 'memory_hits=' in out
    assert 'Elden Ring' in out


def test_sanitize_output():
    raw = '**Bold** text with `code` and extra\n\n\nlines.'
    cleaned = sanitize_output(raw)
    assert '**' not in cleaned
    assert '`' not in cleaned
    assert '\n\n\n' not in cleaned

