"""
YOLO Object Detection Module
Fast real-time object detection for gaming (60+ FPS)
"""

from ultralytics import YOLO
import numpy as np
from PIL import Image
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import time


@dataclass
class Detection:
    """A detected object"""
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center: Tuple[int, int]
    
    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]
    
    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]
        
    @property
    def area(self) -> int:
        return self.width * self.height


class YOLODetector:
    """
    Fast YOLO-based object detection for gaming.
    Runs at 60+ FPS on RTX 5080.
    
    Usage:
        detector = YOLODetector()
        detections = detector.detect(frame)
        
        # Find specific objects
        enemies = detector.find_class(detections, "person")
    """
    
    # COCO class names (default YOLO training)
    COCO_CLASSES = [
        'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 
        'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign', 
        'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 
        'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 
        'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 
        'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 
        'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 
        'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 
        'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 
        'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 
        'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 
        'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 
        'scissors', 'teddy bear', 'hair drier', 'toothbrush'
    ]
    
    def __init__(
        self,
        model_size: str = "s",  # n=nano, s=small, m=medium, l=large, x=xlarge
        confidence_threshold: float = 0.5,
        device: str = "cuda"  # cuda, cpu, or specific GPU
    ):
        self.confidence_threshold = confidence_threshold
        self.device = device
        
        # Load model
        model_name = f"yolo11{model_size}.pt"
        self.model = YOLO(model_name)
        self.model.to(device)
        
        # Warmup
        self._warmup()
        
    def _warmup(self, iterations: int = 3):
        """Warm up the model for consistent performance"""
        dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
        for _ in range(iterations):
            self.model(dummy, verbose=False)
            
    def detect(
        self,
        frame: Any,  # PIL Image, numpy array, or path
        classes: Optional[List[int]] = None  # Filter to specific classes
    ) -> List[Detection]:
        """
        Run detection on a frame.
        
        Args:
            frame: Image to analyze (PIL, numpy, or path)
            classes: Optional list of class IDs to detect
            
        Returns:
            List of Detection objects
        """
        # Run inference
        results = self.model(
            frame,
            verbose=False,
            conf=self.confidence_threshold,
            classes=classes
        )
        
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id]
                
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                
                detections.append(Detection(
                    class_name=cls_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(center_x, center_y)
                ))
                
        return detections
    
    def find_class(
        self,
        detections: List[Detection],
        class_name: str
    ) -> List[Detection]:
        """Filter detections to a specific class"""
        return [d for d in detections if d.class_name == class_name]
    
    def find_nearest(
        self,
        detections: List[Detection],
        point: Tuple[int, int],
        class_name: Optional[str] = None
    ) -> Optional[Detection]:
        """Find detection nearest to a point"""
        if class_name:
            detections = self.find_class(detections, class_name)
            
        if not detections:
            return None
            
        def distance(d: Detection) -> float:
            dx = d.center[0] - point[0]
            dy = d.center[1] - point[1]
            return (dx*dx + dy*dy) ** 0.5
            
        return min(detections, key=distance)
    
    def find_largest(
        self,
        detections: List[Detection],
        class_name: Optional[str] = None
    ) -> Optional[Detection]:
        """Find the largest detection (by area)"""
        if class_name:
            detections = self.find_class(detections, class_name)
            
        if not detections:
            return None
            
        return max(detections, key=lambda d: d.area)
    
    def summarize(self, detections: List[Detection]) -> str:
        """Create a text summary of detections for the LLM"""
        if not detections:
            return "No objects detected"
            
        # Group by class
        by_class: Dict[str, List[Detection]] = {}
        for d in detections:
            if d.class_name not in by_class:
                by_class[d.class_name] = []
            by_class[d.class_name].append(d)
            
        parts = []
        for cls_name, items in by_class.items():
            if len(items) == 1:
                d = items[0]
                parts.append(f"{cls_name} at ({d.center[0]}, {d.center[1]})")
            else:
                parts.append(f"{len(items)} {cls_name}s")
                
        return "Detected: " + ", ".join(parts)
    
    def benchmark(self, frame: Any, iterations: int = 50) -> Dict:
        """Benchmark detection speed"""
        times = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            _ = self.detect(frame)
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
    print("YOLO Detector Test")
    print("="*40)
    
    from capture import ScreenCapture
    
    capture = ScreenCapture(resolution=(1280, 720))
    detector = YOLODetector(model_size="s")
    
    # Capture and detect
    frame = capture.grab_numpy()
    detections = detector.detect(frame)
    
    print(f"Found {len(detections)} objects")
    print(detector.summarize(detections))
    
    # Benchmark
    print("\nBenchmarking...")
    results = detector.benchmark(frame, 50)
    print(f"Average: {results['avg_ms']:.1f}ms ({results['fps']:.1f} FPS)")
