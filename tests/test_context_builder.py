from companion_ai.core.context_builder import extract_keywords

def test_extract_keywords_basic():
    ks = extract_keywords("I really like building useful python tools and like sharing code", limit=4)
    # 'like' may appear but we expect key content words
    assert 'python' in ks and 'tools' in ks
    assert len(ks) <= 4