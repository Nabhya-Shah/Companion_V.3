"""Tests for custom tools - V5 architecture."""
from companion_ai.tools import list_tools, run_tool

def test_list_tools_contains_core():
    """Test that core tools are registered."""
    tools = list_tools()
    # V5 tools: brain_*, memory_search, use_computer, etc.
    assert 'get_current_time' in tools
    assert 'memory_search' in tools  # memory_insight removed, replaced with memory_search
    assert 'brain_read' in tools     # V5 brain tools
    assert 'brain_write' in tools
    assert 'brain_list' in tools
    assert 'wikipedia_lookup' in tools
    assert 'find_file' in tools
    assert 'list_files' in tools
    assert 'use_computer' in tools

def test_time_tool():
    """Test get_current_time tool works."""
    result = run_tool('get_current_time', '')
    # Should return current time info
    assert result is not None
    assert 'Unknown tool' not in result

def test_unknown_tool():
    """Test unknown tool returns error message."""
    result = run_tool('not_a_tool', 'x')
    assert 'Unknown tool' in result