"""Tests for sanitize_output (search tool removed - handled by Compound)."""
import re
from companion_ai.llm_interface import sanitize_output


def test_sanitize_output():
    """Test markdown/formatting cleanup."""
    raw = '**Bold** text with `code` and extra\n\n\nlines.'
    cleaned = sanitize_output(raw)
    assert '**' not in cleaned
    assert '`' not in cleaned
    assert '\n\n\n' not in cleaned


def test_sanitize_preserves_content():
    """Test that sanitize keeps the actual content."""
    raw = '**Important:** This is `code` here'
    cleaned = sanitize_output(raw)
    assert 'Important' in cleaned
    assert 'This is' in cleaned
    assert 'code' in cleaned
    assert 'here' in cleaned

