#!/usr/bin/env python3
"""
Send message to Companion AI via debug API.
Used by AI agent for testing without terminal approval dialogs.

Usage:
    python tools/send_debug_message.py "your message here"
"""

import sys
import requests
import json

def send_message(message: str, base_url='http://localhost:5000'):
    """Send a message to the debug chat API."""
    try:
        response = requests.post(
            f'{base_url}/api/debug/chat',
            json={'message': message},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"You: {data['user']}")
        print(f"AI: {data['ai']}")
        if 'tokens' in data:
            t = data['tokens']
            print(f"[Tokens: In={t.get('input',0)} Out={t.get('output',0)} Total={t.get('total',0)}]")
        print(f"[History: {data['history_length']} messages]")
        print()
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python send_debug_message.py 'your message'")
        sys.exit(1)
    
    message = ' '.join(sys.argv[1:])
    send_message(message)
