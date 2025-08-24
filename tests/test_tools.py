from companion_ai.tools import list_tools, run_tool

def test_list_tools_contains_defaults():
    tools = list_tools()
    assert 'time' in tools and 'calc' in tools

def test_calc_tool_basic():
    assert run_tool('calc', '1+2*3') == '7'
    assert 'error' in run_tool('calc', '1/0')
    assert 'Invalid' in run_tool('calc', 'import os')

def test_unknown_tool():
    assert run_tool('not_a_tool', 'x') == 'unknown tool'