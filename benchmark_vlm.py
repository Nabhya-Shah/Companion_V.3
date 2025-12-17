"""
Vision Model Benchmark for Gaming
Tests VLM speed with Minecraft screenshots

Run with: .venv-gaming\Scripts\python benchmark_vlm.py
"""

import time
import os
import sys
import base64
import requests
from datetime import datetime

# Screen capture
try:
    import mss
    import mss.tools
except ImportError:
    print("Install mss: pip install mss")
    sys.exit(1)


OLLAMA_URL = "http://localhost:11434/api/generate"

MODELS_TO_TEST = [
    "moondream",
    "gemma3:4b", 
    "qwen3-vl:2b",
]

GAMING_PROMPT = """You are a gaming AI. Describe what you see in this Minecraft screenshot in ONE short sentence.
Focus on: terrain, enemies, items, dangers, opportunities.
Be BRIEF - max 20 words."""


def capture_screen() -> str:
    """Capture screen and return as base64"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        
        # Save temporarily
        temp_path = "temp_screenshot.png"
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=temp_path)
        
        # Read as base64
        with open(temp_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        
        # Cleanup
        os.remove(temp_path)
        
        return img_data


def test_model(model: str, image_b64: str) -> dict:
    """Test a single model and return results"""
    print(f"\n  Testing {model}...")
    
    start_time = time.perf_counter()
    
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": GAMING_PROMPT,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 50
                }
            },
            timeout=60
        )
        response.raise_for_status()
        
        elapsed = time.perf_counter() - start_time
        result = response.json().get("response", "").strip()
        
        return {
            "model": model,
            "time": elapsed,
            "response": result,
            "success": True
        }
        
    except requests.exceptions.Timeout:
        return {"model": model, "time": 60, "response": "TIMEOUT", "success": False}
    except Exception as e:
        return {"model": model, "time": 0, "response": str(e), "success": False}


def main():
    print("=" * 60)
    print("  Vision Model Benchmark for Gaming")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Wait 5 seconds (switch to Minecraft!)")
    print("  2. Take a screenshot")
    print("  3. Test each VLM model")
    print("  4. Show timing results")
    print()
    
    # Check which models are installed
    print("Checking installed models...")
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        installed = [m["name"] for m in resp.json().get("models", [])]
        print(f"  Installed: {', '.join(installed)}")
    except:
        print("  Could not check installed models")
        installed = []
    
    # Filter to only test installed models
    models = [m for m in MODELS_TO_TEST if any(m.split(":")[0] in i for i in installed)]
    
    if not models:
        print("\nNo test models installed! Run:")
        print("  ollama pull moondream")
        print("  ollama pull gemma3:4b")
        print("  ollama pull qwen3-vl:2b")
        return
    
    print(f"\nWill test: {', '.join(models)}")
    
    # Countdown
    print("\n" + "=" * 60)
    print("  Switch to Minecraft now!")
    print("=" * 60)
    for i in range(5, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)
    
    # Capture
    print("\n  Capturing screen...")
    image_b64 = capture_screen()
    print("  Screenshot captured!")
    
    # Test each model
    print("\n" + "=" * 60)
    print("  Testing Models")
    print("=" * 60)
    
    results = []
    for model in models:
        result = test_model(model, image_b64)
        results.append(result)
        
        if result["success"]:
            print(f"    Time: {result['time']:.2f}s")
            print(f"    Response: {result['response'][:100]}...")
        else:
            print(f"    FAILED: {result['response']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print()
    print(f"{'Model':<20} {'Time':<10} {'FPS':<8} Response")
    print("-" * 80)
    
    for r in sorted(results, key=lambda x: x["time"]):
        fps = 1.0 / r["time"] if r["time"] > 0 else 0
        status = r["response"][:40] + "..." if len(r["response"]) > 40 else r["response"]
        print(f"{r['model']:<20} {r['time']:.2f}s      {fps:.2f}    {status}")
    
    print()
    
    # Recommendations
    fastest = min(results, key=lambda x: x["time"] if x["success"] else 999)
    if fastest["success"]:
        print(f"FASTEST: {fastest['model']} at {fastest['time']:.2f}s ({1/fastest['time']:.2f} FPS)")
        
        if fastest["time"] < 1.0:
            print("  -> EXCELLENT for gaming!")
        elif fastest["time"] < 3.0:
            print("  -> Good for strategic decisions (not reactions)")
        else:
            print("  -> Too slow for real-time gaming")


if __name__ == "__main__":
    main()
