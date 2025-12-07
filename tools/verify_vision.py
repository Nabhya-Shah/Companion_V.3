#!/usr/bin/env python3
import sys
import os
import time

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.vision_manager import vision_manager

def main():
    print("running vision verification...")
    print(f"model: {vision_manager.vision_model}")
    print(f"api key present: {bool(vision_manager.api_key)}")
    
    start_time = time.time()
    try:
        print("capturing and analyzing screen...")
        result = vision_manager.analyze_current_screen("What is on the screen right now? Be brief.")
        duration = time.time() - start_time
        
        print("\n--- vision result ---")
        print(result)
        print("---------------------")
        print(f"duration: {duration:.2f}s")
        
        if "Error" in result:
            print("FAILED: Vision error returned")
            sys.exit(1)
            
        print("PASS: Vision analysis completed")
        
    except Exception as e:
        print(f"FAILED: Exception occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
