#!/usr/bin/env python3
import sys
import os
import time
import logging

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_computer_use")

from companion_ai.conversation_manager import ConversationSession
from companion_ai.computer_agent import computer_agent
from companion_ai.omni_parser_client import omni_client

def safe_print(msg):
    """Safely print text handling unicode errors on Windows console"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback to ascii approximation or ignore
        try:
            print(msg.encode('ascii', 'ignore').decode('ascii'))
        except:
            print("[Message contained unprintable characters]")

def main():
    safe_print("Running E2E Computer Use Verification...")
    
    # 1. Setup Environment
    computer_agent.enabled = True
    computer_agent.safe_mode = True 
    safe_print(f"Computer Agent Enabled: {computer_agent.enabled}")
    safe_print(f"Safe Mode: {computer_agent.safe_mode}")
    safe_print(f"OmniParser Available: {omni_client.available}")
    
    # 2. Initialize Session
    session = ConversationSession()
    
    # 3. Simulate User Request
    user_msg = "Please open File Explorer for me."
    safe_print(f"\nUser: {user_msg}")
    safe_print("... Planner is thinking ...")
    
    start_t = time.time()
    
    try:
        response, _ = session.process_message(user_msg, [])
        duration = time.time() - start_t
        
        safe_print(f"\nAI Response: {response}")
        safe_print(f"Duration: {duration:.2f}s")
        
        # 4. Verify Trace
        if "Explorer" in response or "opening" in response.lower() or "click" in response.lower():
             safe_print("\nPASS: AI acknowledged the action.")
        else:
             safe_print("\nWARN: AI might not have executed the tool. Check logs.")

    except Exception as e:
        safe_print(f"\nFAIL: Error during processing: {e}")
        # Print stack trace if needed, but safely
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
