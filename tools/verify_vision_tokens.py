#!/usr/bin/env python3
import sys
import os
import time
from datetime import datetime

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.vision_manager import vision_manager

def main():
    print("running vision token verification...")
    
    if not vision_manager.client:
        print("Error: Vision API client not initialized (check API key)")
        sys.exit(1)
        
    start_time = time.time()
    
    # We need to capture the response object to get token usage
    # The current vision_manager.analyze_current_screen returns string only
    # So we will access the internal client directly to measure usage for a test image
    
    print("\n--- TEST 1: High Detail (1024px) ---")
    img_1024 = vision_manager.capture_screen(resize_dim=1024)
    b64_1024 = vision_manager._image_to_base64(img_1024)
    
    try:
        response = vision_manager.client.chat.completions.create(
            model=vision_manager.vision_model,
            messages=[{"role": "user", "content": [{"type": "text", "text": "Describe."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_1024}"}}]}],
            max_tokens=10, temperature=0.1
        )
        print(f"Tokens (1024px): {response.usage.total_tokens}")
    except Exception as e: print(e)

    print("\n--- TEST 2: Optimized (768px) ---")
    img_768 = vision_manager.capture_screen(resize_dim=768)
    b64_768 = vision_manager._image_to_base64(img_768)
    
    try:
        response = vision_manager.client.chat.completions.create(
            model=vision_manager.vision_model,
            messages=[{"role": "user", "content": [{"type": "text", "text": "Describe."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_768}"}}]}],
            max_tokens=10, temperature=0.1
        )
        print(f"Tokens (768px): {response.usage.total_tokens}")
    except Exception as e: print(e)

if __name__ == "__main__":
    main()
