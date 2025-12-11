#!/usr/bin/env python3
"""
Check Local Models
------------------
Verifies that Ollama is running and the required models for the Companion
are installed and working.
"""

import sys
import os
import time
import requests

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion_ai.local_llm import get_local_llm, OllamaBackend

REQUIRED_MODELS = {
    "llama3.1:latest": "Primary Agent (Tools/Control)",
    "minicpm-v:latest": "Vision (The 'Eyes')",
    # Optional but recommended
    "qwen2.5:14b": "Heavy Reasoning (Optional)"
}

def check_ollama():
    print("🔍 Checking Ollama status...")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("✅ Ollama is running!")
            return True
        else:
            print(f"❌ Ollama returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Ollama is NOT running.")
        print("   Please start it with 'ollama serve' or the desktop app.")
        return False

def check_models():
    print("\n🔍 Checking installed models...")
    try:
        response = requests.get("http://localhost:11434/api/tags")
        installed_models = [m['name'] for m in response.json().get('models', [])]
        
        all_good = True
        for model, description in REQUIRED_MODELS.items():
            # Handle tag variations (e.g. llama3.1:latest vs llama3.1)
            base_name = model.split(':')[0]
            found = False
            for installed in installed_models:
                if installed == model or installed.startswith(base_name):
                    print(f"✅ Found {description}: {installed}")
                    found = True
                    break
            
            if not found:
                print(f"❌ MISSING {description}: {model}")
                print(f"   Run: ollama pull {model}")
                if "Optional" not in description:
                    all_good = False
        
        return all_good
    except Exception as e:
        print(f"❌ Error checking models: {e}")
        return False

def test_inference():
    print("\n🧪 Testing inference (llama3.1)...")
    llm = get_local_llm()
    if not llm.is_available():
        print("❌ Local LLM backend not available.")
        return

    start = time.time()
    try:
        response = llm.generate("Say 'Hello, Companion!' and nothing else.", model="llama3.1:latest")
        duration = time.time() - start
        print(f"✅ Response ({duration:.2f}s): {response}")
    except Exception as e:
        print(f"❌ Inference failed: {e}")

if __name__ == "__main__":
    print("="*50)
    print("🛠️  LOCAL MODEL DIAGNOSTIC")
    print("="*50)
    
    if check_ollama():
        if check_models():
            test_inference()
            print("\n✨ System is ready for local compute!")
        else:
            print("\n⚠️  Some models are missing. Please pull them.")
    else:
        print("\n🛑 Cannot proceed without Ollama.")
