#!/usr/bin/env python3
import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.computer_agent import computer_agent
from companion_ai.omni_parser_client import omni_client
from companion_ai.grid_overlay import GridOverlay
from companion_ai.vision_manager import vision_manager

def main():
    print("running natural agent verification...")
    
    # 1. Check OmniParser
    print(f"OmniParser Status: {'ONLINE' if omni_client.available else 'OFFLINE (Expected if not started)'}")
    
    # 2. Test Locate (Safe Mode)
    computer_agent.safe_mode = True
    computer_agent.enabled = True
    
    target = "Taskbar"
    print(f"\n--- Test Locate '{target}' ---")
    start_t = time.time()
    coords = computer_agent.locate_element(target)
    duration = time.time() - start_t
    
    if coords:
        print(f"PASS: Found at: {coords} in {duration:.2f}s")
    else:
        print(f"FAIL: Not found (check logs)")
        
    # 3. Test Grid Generation
    print("\n--- Test Grid Overlay ---")
    img = vision_manager.capture_screen(resize_dim=800)
    grid_img, grid_map = GridOverlay.overlay_grid(img, rows=3, cols=3)
    print(f"Grid Map Generated: {len(grid_map)} cells")
    print(f"Cell 5 Center: {grid_map.get(5)}")
    
    # Save grid image for inspection if needed
    save_path = "tools/test_grid.png"
    grid_img.save(save_path)
    print(f"Saved test grid to {save_path}")

if __name__ == "__main__":
    main()
