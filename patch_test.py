import pytest
from companion_ai.memory.sqlite_backend import rank_memories_by_quality

def test_explainable_recall_signals_mocked(monkeypatch):
    memories = [
        {'id': 'mem-1', 'memory': 'I live in Lisbon', 'score': 0.8}
    ]
    def mock_get_memory_quality_map(scope):
        return {
            'mem-1': {'confidence': 0.95, 'confidence_label': 'high', 'contradiction_state': 'none'}
        }
    
    monkeypatch.setattr('companion_ai.memory.sqlite_backend.get_memory_quality_map', mock_get_memory_quality_map)
    ranked = rank_memories_by_quality(memories, 'user', query='Lisbon')
    
    assert len(ranked) == 1
    assert 'score_breakdown' in ranked[0]
    assert 'surfacing_reason' in ranked[0]
    assert 'High' in ranked[0]['surfacing_reason']
    assert 'query match' in ranked[0]['surfacing_reason'].lower()
