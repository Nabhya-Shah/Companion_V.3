#!/usr/bin/env python3
"""
Comprehensive feature test script.
Tests all implemented features by sending actual messages to the server.

This script should be run while the server is running via test_server_interactive.py

Features tested:
1. Token optimization (check logs for input token counts)
2. Weather tool (Groq Compound server-side execution)
3. Calculator (basic tool)
4. Sequential tools (find → read PDF)
5. Knowledge graph memory_insight with different modes
6. Web search
7. Time tool
8. Multi-tool workflows
"""

import requests
import time
import sys
from pathlib import Path

# Server config
BASE_URL = "http://localhost:5000"
DEBUG_ENDPOINT = f"{BASE_URL}/api/debug/chat"

def send_message(message: str, delay: float = 3.0):
    """Send a message and wait for response"""
    print(f"\n{'='*70}")
    print(f"📤 SENDING: {message}")
    print(f"{'='*70}")
    
    try:
        response = requests.post(
            DEBUG_ENDPOINT,
            json={"message": message},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            reply = data.get('response', 'No response')
            print(f"✅ RESPONSE: {reply}")
            
            # Show tool info if available
            if 'tool_used' in data and data['tool_used']:
                print(f"🔧 Tool used: {data['tool_used']}")
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(response.text)
    
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server")
        print("Make sure the server is running with: python tools/test_server_interactive.py")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Wait before next test
    if delay > 0:
        print(f"\n⏳ Waiting {delay}s before next test...")
        time.sleep(delay)

def main():
    print("=" * 70)
    print("🧪 COMPREHENSIVE FEATURE TEST")
    print("=" * 70)
    print("\nThis will test all implemented features.")
    print("Make sure the server is running with: python tools/test_server_interactive.py")
    print("\nPress Enter to start, or Ctrl+C to cancel...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n\nTest cancelled")
        return 1
    
    tests = [
        # Test 1: Weather tool (Compound system + token optimization)
        {
            "name": "Weather Tool (Compound + Token Optimization)",
            "message": "What's the weather in Tokyo right now?",
            "delay": 4
        },
        
        # Test 2: Calculator (basic tool)
        {
            "name": "Calculator Tool",
            "message": "Calculate 9876 times 543",
            "delay": 3
        },
        
        # Test 3: Time tool
        {
            "name": "Time Tool",
            "message": "What time is it right now?",
            "delay": 3
        },
        
        # Test 4: Knowledge graph - GRAPH_COMPLETION mode
        {
            "name": "Knowledge Graph (GRAPH_COMPLETION)",
            "message": "What do you know about Python? Use memory_insight with GRAPH_COMPLETION mode",
            "delay": 4
        },
        
        # Test 5: Knowledge graph - RELATIONSHIPS mode
        {
            "name": "Knowledge Graph (RELATIONSHIPS)",
            "message": "How are User and Python related? Use memory_insight with RELATIONSHIPS mode",
            "delay": 4
        },
        
        # Test 6: Knowledge graph - IMPORTANT mode
        {
            "name": "Knowledge Graph (IMPORTANT)",
            "message": "What are the most important things in my memory? Use memory_insight with IMPORTANT mode",
            "delay": 4
        },
        
        # Test 7: Multi-tool workflow
        {
            "name": "Multi-Tool Workflow (Weather + Calculator)",
            "message": "What's the temperature in Paris in Fahrenheit, then calculate that number times 2?",
            "delay": 5
        },
        
        # Test 8: Sequential tools (if PDF exists)
        {
            "name": "Sequential Tools (Find + Read)",
            "message": "Find any PDF files and tell me what one of them is about",
            "delay": 5
        },
        
        # Test 9: Simple conversation (no tools)
        {
            "name": "Simple Conversation (No Tools)",
            "message": "Hi! How are you doing today?",
            "delay": 3
        },
        
        # Test 10: Natural synthesis check
        {
            "name": "Natural Synthesis Check",
            "message": "What's the weather in Seattle and is it a good day for a walk?",
            "delay": 4
        }
    ]
    
    print(f"\n🚀 Starting {len(tests)} tests...\n")
    
    for i, test in enumerate(tests, 1):
        print(f"\n{'#'*70}")
        print(f"# TEST {i}/{len(tests)}: {test['name']}")
        print(f"{'#'*70}")
        send_message(test['message'], test.get('delay', 3))
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 70)
    print("\nReview the results:")
    print("1. Check console output above for responses")
    print("2. View full server log: python tools/view_test_log.py")
    print("3. Check token usage: python tools/view_test_log.py --filter 'input_tokens'")
    print("4. View statistics: python tools/view_test_log.py --stats")
    print("\nTo stop the server, go to the test_server_interactive.py window and press Ctrl+C")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
