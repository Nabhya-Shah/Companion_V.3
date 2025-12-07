#!/usr/bin/env python3
import sys
import os
import time
import logging

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_live")

from companion_ai.conversation_manager import ConversationSession
from companion_ai.computer_agent import computer_agent

def safe_print(msg):
    try:
        print(msg)
    except:
        print(msg.encode('ascii', 'ignore').decode('ascii'))

def main():
    safe_print("\n⚠️  LIVE COMPUTER CONTROL DEMO ⚠️")
    safe_print("This script will give the AI REAL control of your mouse/keyboard.")
    safe_print("Please DO NOT touch the mouse/keyboard while it runs.")
    safe_print("Move your mouse to the corner of the screen to abort (Failsafe).\n")
    
    # 1. Setup Live Environment
    computer_agent.enabled = True
    computer_agent.safe_mode = False  # <--- LIVE MODE
    safe_print(f"Computer Agent Enabled: {computer_agent.enabled}")
    safe_print(f"Safe Mode: {computer_agent.safe_mode} (REAL ACTIONS ENABLED)")
    
    # 2. Initialize Session
    session = ConversationSession()
    
    # 3. Request
    # Explicitly asking for the sequence to test reliability
    user_msg = "Launch Notepad, type 'hi', then close it without saving."
    safe_print(f"\nUser: {user_msg}")
    safe_print("... AI Processing ...")
    safe_print("👀 WATCH YOUR SCREEN NOW! (Action in 5s)...")
    time.sleep(5)
    
    start_t = time.time()
    try:
        # Increase timeout/iterations for this multi-step task
        response, _ = session.process_message(user_msg, [])  # Now returns 3 args sometimes? 
        # Wait, process_message returns (str, bool) in conversation_manager.py
        # But generate_model_response_with_tools returned 3.
        # Let's check conversation_manager return signature.
        # It calls generate_response which returns str.
        # process_message returns (response, memory_saved).
    except ValueError:
        # Handle unpacking if I messed up my memory.
        # Re-check conversation_manager.py: "return ai_response, memory_saved"
        # So it returns 2 values.
        try:
             response, _ = session.process_message(user_msg, [])
        except:
             # Just in case
             response = session.process_message(user_msg, [])
             if isinstance(response, tuple):
                 response = response[0]

    duration = time.time() - start_t
    
    safe_print(f"\nAI Response: {response}")
    safe_print(f"Duration: {duration:.2f}s")
    
    safe_print("\nDemo Complete.")

if __name__ == "__main__":
    main()
