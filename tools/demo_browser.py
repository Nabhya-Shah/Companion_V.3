import sys
import os
import time
import logging

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.conversation_manager import ConversationSession
from companion_ai.computer_agent import computer_agent
from companion_ai.vision_manager import vision_manager

# Configure logging to show what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("BrowserDemo")

def run_browser_test():
    """
    Execute the Browser Integration Test:
    1. Open Chrome
    2. Go to Wikipedia
    3. Search for Cheeseburger
    """
    print("=======================================================")
    print(" CHROME STARTING: WIKIPEDIA CHEESEBURGER TEST ")
    print("=======================================================")
    
    # 1. Initialize
    session = ConversationSession()
    computer_agent.enabled = True
    computer_agent.safe_mode = False # LIVE MODE
    
    # 2. Define the multi-step prompt
    prompt = (
        "Open the 'Chrome' browser using the launch tool. "
        "Then type 'wikipedia.org' and press Enter. "
        "Wait for it to load. "
        "Then find the search bar, click it, and search for 'cheeseburger'."
    )
    
    # 3. Execution Loop
    print(f"\nUser Request: {prompt}\n")
    
    max_turns = 8
    current_prompt = prompt
    
    for i in range(max_turns):
        print(f"\n--- Turn {i+1}/{max_turns} ---")
        
        # Monitor: What does the agent see?
        print("👀 Agent is looking at the screen...")
        
        # Execute
        response, _ = session.process_message(current_prompt, [])
        print(f"🤖 Agent: {response}")
        
        if "completed" in response.lower() or "searched" in response.lower():
            print("\n✅ Test seemingly complete.")
            break
            
        # Give it a moment to realize the state changed
        time.sleep(2)
        
        # Continue the conversation (Agent is loop-based)
        current_prompt = "Continue. What is the next step to achieve the goal?"

if __name__ == "__main__":
    try:
        run_browser_test()
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user.")
