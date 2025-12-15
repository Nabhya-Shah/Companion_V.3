"""Vision Model A/B Test - Compare minicpm-v, llama3.2-vision, and llava:13b"""
import time
import os
from datetime import datetime

# Capture a screenshot first
from PIL import ImageGrab
import tempfile

print("[*] Capturing screenshot...")
screenshot = ImageGrab.grab()
screenshot_path = os.path.join(tempfile.gettempdir(), "vision_test_screen.png")
screenshot.save(screenshot_path)
print(f"Screenshot saved: {screenshot_path}")

# Test prompt - something useful for computer control
TEST_PROMPT = "Describe what you see on this screen. List any visible text, buttons, windows, and their positions. Be specific about what the user is currently looking at."

# Import local LLM
from companion_ai.local_llm import get_local_llm

llm = get_local_llm()

MODELS = [
    "minicpm-v:latest",
    "llama3.2-vision:latest", 
    "llava:13b"
]

results = {}

for model in MODELS:
    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        response = llm.analyze_image(TEST_PROMPT, screenshot_path, model=model)
        elapsed = time.time() - start
        results[model] = {
            "response": response[:500] + "..." if len(response) > 500 else response,
            "time": round(elapsed, 2),
            "success": True
        }
        print(f"Time: {elapsed:.2f}s")
        print(f"Response: {response[:300]}...")
    except Exception as e:
        elapsed = time.time() - start
        results[model] = {
            "error": str(e),
            "time": round(elapsed, 2),
            "success": False
        }
        print(f"ERROR: {e}")

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for model, data in results.items():
    status = "OK" if data["success"] else "FAIL"
    print(f"{model}: {status} ({data['time']}s)")

# Save results
output_file = os.path.join(os.path.dirname(__file__), "..", "data", "vision_test_results.txt")
with open(output_file, "w") as f:
    f.write(f"Vision Model A/B Test - {datetime.now()}\n")
    f.write("="*60 + "\n\n")
    for model, data in results.items():
        f.write(f"Model: {model}\n")
        f.write(f"Time: {data['time']}s\n")
        if data["success"]:
            f.write(f"Response:\n{data['response']}\n")
        else:
            f.write(f"Error: {data.get('error', 'Unknown')}\n")
        f.write("\n" + "-"*40 + "\n\n")

print(f"\nResults saved to: {output_file}")
