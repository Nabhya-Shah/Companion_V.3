"""
Screen Capture Module
Fast screen capture using MSS for gaming vision
"""

import mss
import mss.tools
from PIL import Image
import numpy as np
from typing import Optional, Tuple
import time


class ScreenCapture:
    """
    High-performance screen capture for gaming.
    Uses MSS for fast multi-monitor support.
    
    Note: MSS is thread-local, so we lazy-init it on first use.
    
    Usage:
        capture = ScreenCapture(resolution=(1280, 720))
        frame = capture.grab()  # Get PIL Image
        frame_np = capture.grab_numpy()  # Get numpy array for YOLO
    """
    
    def __init__(
        self,
        resolution: Tuple[int, int] = (1280, 720),
        monitor: int = 1,  # 0 = all, 1 = primary, 2+ = others
        center_crop: bool = True
    ):
        self.resolution = resolution
        self.monitor_index = monitor
        self.center_crop = center_crop
        self._sct = None  # Lazy init for thread safety
        self._last_frame_time = 0
        self._frame_count = 0
        
    def _get_sct(self):
        """Get or create MSS instance (thread-safe lazy init)"""
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct
        
    @property
    def monitor(self) -> dict:
        """Get monitor info"""
        return self._get_sct().monitors[self.monitor_index]
        
    def _get_region(self) -> dict:
        """Calculate capture region (centered)"""
        mon = self.monitor
        
        if self.center_crop:
            # Center crop to target resolution
            width, height = self.resolution
            left = (mon["width"] - width) // 2 + mon["left"]
            top = (mon["height"] - height) // 2 + mon["top"]
        else:
            # Full monitor, will resize later
            left = mon["left"]
            top = mon["top"]
            width = mon["width"]
            height = mon["height"]
            
        return {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }
        
    def grab(self) -> Image.Image:
        """Capture screen as PIL Image (RGB)"""
        region = self._get_region()
        screenshot = self._get_sct().grab(region)
        
        # Convert BGRA to RGB PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        # Resize if not center cropping
        if not self.center_crop and img.size != self.resolution:
            img = img.resize(self.resolution, Image.Resampling.LANCZOS)
            
        self._frame_count += 1
        self._last_frame_time = time.time()
        
        return img
        
    def grab_numpy(self) -> np.ndarray:
        """Capture screen as numpy array (RGB, HWC format for YOLO)"""
        region = self._get_region()
        screenshot = self._get_sct().grab(region)
        
        # Convert to numpy array (BGRA)
        img = np.array(screenshot)
        
        # Convert BGRA to RGB
        img = img[:, :, [2, 1, 0]]
        
        # Resize if needed
        if not self.center_crop and (img.shape[1], img.shape[0]) != self.resolution:
            from PIL import Image as PILImage
            pil_img = PILImage.fromarray(img)
            pil_img = pil_img.resize(self.resolution, PILImage.Resampling.LANCZOS)
            img = np.array(pil_img)
            
        self._frame_count += 1
        self._last_frame_time = time.time()
        
        return img
        
    def save_frame(self, path: str) -> str:
        """Capture and save to file"""
        img = self.grab()
        img.save(path)
        return path
        
    @property
    def fps(self) -> float:
        """Estimated FPS based on frame timing"""
        if self._frame_count < 2:
            return 0.0
        # This is just tracking, not actual measurement
        return self._frame_count
        
    def benchmark(self, frames: int = 100) -> dict:
        """Benchmark capture speed"""
        times = []
        
        for _ in range(frames):
            start = time.perf_counter()
            _ = self.grab_numpy()
            end = time.perf_counter()
            times.append((end - start) * 1000)
            
        avg = sum(times) / len(times)
        return {
            "avg_ms": avg,
            "fps": 1000 / avg,
            "min_ms": min(times),
            "max_ms": max(times)
        }


# Quick test
if __name__ == "__main__":
    print("Screen Capture Test")
    print("="*40)
    
    capture = ScreenCapture(resolution=(1280, 720))
    
    print(f"Monitor: {capture.monitor['width']}x{capture.monitor['height']}")
    print(f"Capture resolution: {capture.resolution}")
    
    # Benchmark
    print("\nBenchmarking (100 frames)...")
    results = capture.benchmark(100)
    print(f"Average: {results['avg_ms']:.1f}ms")
    print(f"FPS: {results['fps']:.1f}")
    
    # Save a test frame
    capture.save_frame("test_capture.png")
    print("\nSaved test frame to: test_capture.png")
