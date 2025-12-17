"""
Staggered VLM Pipeline Benchmark
Tests if pipelining multiple VLM requests can give faster effective updates

Run with: .venv-gaming\Scripts\python benchmark_pipeline.py
"""

import time
import os
import sys
import base64
import threading
import queue
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    import mss
    import mss.tools
except ImportError:
    print("Install mss: pip install mss")
    sys.exit(1)


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:4b"
NUM_WORKERS = 3  # 3 concurrent requests
STAGGER_DELAY = 1.6  # Start new request every 1.6s (5s / 3 workers)

GAMING_PROMPT = """Describe this Minecraft screenshot in ONE sentence (max 15 words).
Focus on: terrain, water, trees, buildings, mobs, time of day."""


class ScreenCapture:
    """Thread-safe screen capture"""
    def __init__(self):
        self._lock = threading.Lock()
        
    def capture(self) -> str:
        """Capture screen and return as base64"""
        with self._lock:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                temp_path = f"temp_ss_{threading.current_thread().name}.png"
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=temp_path)
                with open(temp_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                os.remove(temp_path)
                return img_data


class VLMWorker:
    """A single VLM worker that processes images"""
    def __init__(self, worker_id: int, result_queue: queue.Queue):
        self.worker_id = worker_id
        self.result_queue = result_queue
        self.capture = ScreenCapture()
        
    def process(self, request_id: int) -> dict:
        """Capture screen and get VLM response"""
        start_time = time.perf_counter()
        capture_time = datetime.now().strftime("%H:%M:%S")
        
        # Capture current screen
        image_b64 = self.capture.capture()
        
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": GAMING_PROMPT,
                    "images": [image_b64],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 30
                    }
                },
                timeout=30
            )
            response.raise_for_status()
            
            elapsed = time.perf_counter() - start_time
            result = response.json().get("response", "").strip()
            
            return {
                "request_id": request_id,
                "worker_id": self.worker_id,
                "capture_time": capture_time,
                "elapsed": elapsed,
                "response": result,
                "success": True
            }
            
        except Exception as e:
            return {
                "request_id": request_id,
                "worker_id": self.worker_id,
                "capture_time": capture_time,
                "elapsed": time.perf_counter() - start_time,
                "response": str(e),
                "success": False
            }


def run_pipeline(duration: int = 30):
    """Run staggered pipeline for specified duration"""
    print("=" * 70)
    print("  STAGGERED VLM PIPELINE TEST")
    print("=" * 70)
    print(f"  Model: {MODEL}")
    print(f"  Workers: {NUM_WORKERS}")
    print(f"  Stagger delay: {STAGGER_DELAY}s")
    print(f"  Duration: {duration}s")
    print()
    print("  Switch to Minecraft now!")
    print("=" * 70)
    
    # Countdown
    for i in range(5, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)
    
    print("\n  RUNNING - Walk around in Minecraft!\n")
    print("-" * 70)
    print(f"{'Time':<10} {'Worker':<8} {'Latency':<10} {'Description'}")
    print("-" * 70)
    
    result_queue = queue.Queue()
    workers = [VLMWorker(i, result_queue) for i in range(NUM_WORKERS)]
    results = []
    
    start_time = time.time()
    request_id = 0
    
    # Use thread pool for concurrent requests
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = []
        last_stagger = 0
        
        while time.time() - start_time < duration:
            current_time = time.time() - start_time
            
            # Start new request if stagger delay passed
            if current_time - last_stagger >= STAGGER_DELAY:
                worker = workers[request_id % NUM_WORKERS]
                future = executor.submit(worker.process, request_id)
                futures.append(future)
                request_id += 1
                last_stagger = current_time
            
            # Check for completed results
            new_futures = []
            for future in futures:
                if future.done():
                    result = future.result()
                    results.append(result)
                    
                    # Print result
                    elapsed_total = time.time() - start_time
                    response_preview = result["response"][:45] + "..." if len(result["response"]) > 45 else result["response"]
                    print(f"{elapsed_total:>6.1f}s   W{result['worker_id']}      {result['elapsed']:.2f}s      {response_preview}")
                else:
                    new_futures.append(future)
            futures = new_futures
            
            time.sleep(0.1)
        
        # Wait for remaining futures
        for future in futures:
            result = future.result()
            results.append(result)
    
    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    
    if results:
        successful = [r for r in results if r["success"]]
        if successful:
            avg_latency = sum(r["elapsed"] for r in successful) / len(successful)
            
            # Calculate effective update rate
            if len(successful) > 1:
                first_result_time = successful[0]["elapsed"]
                total_results = len(successful)
                effective_rate = (total_results - 1) / (duration - first_result_time) if duration > first_result_time else 0
            else:
                effective_rate = 0
            
            print(f"  Total results: {len(successful)}")
            print(f"  Avg latency per request: {avg_latency:.2f}s")
            print(f"  Effective update rate: 1 result every {1/effective_rate:.2f}s" if effective_rate > 0 else "  Not enough results")
            print()
            
            if effective_rate > 0 and 1/effective_rate < 2:
                print("  ✓ SUCCESS! Getting updates faster than 2s!")
            elif effective_rate > 0 and 1/effective_rate < 3:
                print("  ~ OKAY - Getting updates every 2-3s")
            else:
                print("  ✗ Still slow - pipeline not helping much")
    else:
        print("  No results collected!")
    
    print()


if __name__ == "__main__":
    # Check if model is available
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if not any(MODEL.split(":")[0] in m for m in models):
            print(f"Model {MODEL} not found! Run: ollama pull {MODEL}")
            sys.exit(1)
    except:
        print("Ollama not running!")
        sys.exit(1)
    
    run_pipeline(duration=30)
