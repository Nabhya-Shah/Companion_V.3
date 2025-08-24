import os, tempfile
from companion_ai import memory as mem

# Basic smoke test for summary/insight dedup mechanics

def test_summary_deduplication():
    mem.clear_all_memory()
    text = "User likes Python and fast models."
    mem.add_summary(text, 0.5)
    # Second add should skip as duplicate
    mem.add_summary(text, 0.7)
    summaries = mem.get_latest_summary(5)
    assert len([s for s in summaries if 'Python' in s['summary_text']]) == 1

def test_insight_similarity_skip():
    mem.clear_all_memory()
    base = "User prefers concise answers about coding patterns."
    mem.add_insight(base, 'preferences', 0.6)
    near = "User prefers concise answers about coding pattern"  # very similar
    mem.add_insight(near, 'preferences', 0.6)
    insights = mem.get_latest_insights(10)
    # Only one similar insight should exist
    matches = [i for i in insights if 'concise answers' in i['insight_text']]
    assert len(matches) == 1
