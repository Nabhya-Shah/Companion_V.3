#!/usr/bin/env python3
"""
Interactive Web + Terminal Mode for Companion AI

Runs Flask web server in background thread while providing
a live terminal chat interface. Both share the same conversation history.

Usage:
    python web_interactive.py
    
Or via launcher:
    python run_companion.py --web-interactive
"""

import threading
import time
import sys
import os
from datetime import datetime

# Import the web companion app
from web_companion import app, conversation_history, logger
from companion_ai.llm_interface import generate_response
from companion_ai.core import config as core_config
from companion_ai import memory as db

def start_web_server(host='localhost', port=5000):
    """Start Flask server in background thread."""
    print(f"🌐 Starting web server at http://{host}:{port}")
    app.run(debug=False, host=host, port=port, use_reloader=False)

def terminal_chat_loop():
    """Interactive terminal chat that shares conversation_history with web."""
    print("\n" + "="*60)
    print("🤖 COMPANION AI - Interactive Terminal Mode")
    print("="*60)
    print("Web UI: http://localhost:5000")
    print("Type your messages here. They'll appear in both terminal and web UI.")
    print("Commands: /exit, /quit, /clear")
    print("="*60 + "\n")
    
    while True:
        try:
            # Prompt for input
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
                
            # Handle commands
            if user_input.lower() in ['/exit', '/quit']:
                print("\n👋 Goodbye!")
                os._exit(0)  # Force exit all threads
                
            if user_input.lower() == '/clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                print("Terminal cleared. Conversation history preserved.\n")
                continue
            
            # Build context from recent conversation
            recent_turns = []
            for entry in conversation_history[-3:]:
                recent_turns.append(f"User: {entry['user']}")
                recent_turns.append(f"AI: {entry['ai']}")
            recent_context = "\n".join(recent_turns) if recent_turns else ""
            
            memory_context = {
                'profile': db.get_all_profile_facts(),
                'summaries': db.get_latest_summary(3),
                'insights': db.get_latest_insights(3),
                'recent_conversation': recent_context
            }
            
            # Generate response
            print("AI: ", end="", flush=True)
            
            try:
                ai_response = generate_response(
                    user_input, 
                    memory_context, 
                    model=None,  # Auto-select
                    persona='Companion'
                )
                
                print(ai_response)
                
                # Add to shared conversation history
                entry = {
                    'user': user_input,
                    'ai': ai_response,
                    'timestamp': datetime.now().isoformat(),
                    'persona': 'Companion',
                    'source': 'terminal'
                }
                conversation_history.append(entry)
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(error_msg)
                logger.error(f"Terminal chat error: {e}")
                
            print()  # Blank line for readability
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            os._exit(0)
        except EOFError:
            print("\n\n👋 EOF detected. Goodbye!")
            os._exit(0)

def main():
    """Start web server in background, then run terminal chat loop."""
    # Start web server thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Give server a moment to start
    time.sleep(2)
    
    # Run terminal chat in foreground
    terminal_chat_loop()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
