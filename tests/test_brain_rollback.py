import pytest
from pathlib import Path
from companion_ai.brain.manager import BrainManager
import os

@pytest.fixture
def brain_mgr(tmp_path):
    mgr = BrainManager(base_path=tmp_path)
    yield mgr

def test_rollback_last_change_creates_file(brain_mgr):
    # Test that rollback successfully undoes a new file write
    brain_mgr.write("test_file.txt", "Hello World")
    assert brain_mgr.read("test_file.txt") == "<!-- Updated: " + str(brain_mgr._last_transaction["path"].read_text().split('Updated: ')[1][:16]) + " -->\nHello World"
    
    # Rollback
    result = brain_mgr.rollback_last_change()
    assert result is True
    
    # File should be removed because it didn't exist before
    content = brain_mgr.read("test_file.txt")
    assert content is None

def test_rollback_last_change_updates_existing(brain_mgr):
    brain_mgr.write("test2.txt", "Initial State")
    
    # Give it a new change
    brain_mgr.write("test2.txt", "Next State")
    
    # Rollback
    assert brain_mgr.rollback_last_change() is True
    assert "Initial State" in brain_mgr.read("test2.txt")
