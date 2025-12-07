#!/usr/bin/env python3
import sys
import os
import time

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.computer_agent import computer_agent
from companion_ai.tools import tool_use_computer

def main():
    print("running computer use verification...")
    # Ensure safe mode is ON
    computer_agent.safe_mode = True
    computer_agent.enabled = True # Needs to be enabled to work
    
    print(f"Safe Mode: {computer_agent.safe_mode}")
    print(f"Screen Size: {computer_agent.screen_width}x{computer_agent.screen_height}")
    
    # Test 1: Click
    # We ask to click something likely to be on screen.
    # The vision mode will analyze the current screen.
    # Note: If no specific element is guaranteed, we might get 'not found', but lets try "Taskbar" or "Start"
    target = "Taskbar"
    print(f"\n--- Test 1: Click '{target}' ---")
    
    start_t = time.time()
    result = tool_use_computer(action="click", text=target)
    duration = time.time() - start_t
    
    print(f"Result: {result}")
    print(f"Duration: {duration:.2f}s")
    
    if "[SAFE MODE]" in result:
        print("PASS: Safe mode click simulated")
    elif "Could not find" in result:
        print("WARN: Element not found (vision issue?), but tool executed")
    else:
        print("FAIL: Unexpected output")
        
    # Test 2: Type
    print(f"\n--- Test 2: Type ---")
    result = tool_use_computer(action="type", text="Hello World")
    print(f"Result: {result}")
    
    if "Would have typed" in result:
        print("PASS: Safe mode type simulated")

if __name__ == "__main__":
    main()
