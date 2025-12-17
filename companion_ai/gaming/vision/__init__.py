"""Vision submodule for gaming - YOLO + VLM hybrid"""

from .capture import ScreenCapture
from .yolo import YOLODetector

__all__ = ['ScreenCapture', 'YOLODetector']
