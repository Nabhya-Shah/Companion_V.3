import pytest
from companion_ai.runtime.computer import ComputerAgent

def test_launch_app_blocking_destructive_commands():
    mgr = ComputerAgent()
    
    # Should block dangerous commands
    assert "launch failed" in mgr.launch_app("rm -rf /")
    assert "launch failed" in mgr.launch_app("mkfs.ext4 /dev/sda1")
    assert "launch failed" in mgr.launch_app("dd if=/dev/zero of=/dev/sda")
    assert "launch failed" in mgr.launch_app("del /s /q C:\\Windows")
    
    # Should allow safe commands
    result = mgr.launch_app("echo hello")
    assert "launch failed" not in result
