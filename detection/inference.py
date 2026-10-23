import os

import cv2
from ultralytics import YOLO

from config import Config


def _normalize_confidence_threshold(confidence_threshold):
    try:
        value = float(confidence_threshold)
    except (TypeError, ValueError):
        value = 0.5
    return max(0.0, min(1.0, value))


class Inference:
    def __init__(self, model_path=None, confidence_threshold=0.5):
        self.model_path = model_path or Config.MODEL_PATH
        if not self.model_path or not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found at {self.model_path}")

        self.model = YOLO(self.model_path)
        self.confidence_threshold = _normalize_confidence_threshold(confidence_threshold)

    def run_inference(self, frame):
        if frame is None:
            return []

        if isinstance(frame, (str, os.PathLike)):
            frame = cv2.imread(str(frame))
            if frame is None:
                return []

        results = self.model(frame, conf=self.confidence_threshold, imgsz=640, verbose=False)
        if not results or len(results) == 0:
            return []

        detections = results[0].boxes
        if detections is None:
            return []

        filtered_detections = []
        for detection in detections:
            confidence = float(detection.conf)
            if confidence < self.confidence_threshold:
                continue
            filtered_detections.append({
                "class_id": int(detection.cls),
                "confidence": confidence,
                "bbox": detection.xyxy[0].tolist(),
            })
        return filtered_detections

    def release_model(self):
        self.model = None


def run_inference(frame, model_path=None, confidence_threshold=0.5):
    engine = Inference(model_path=model_path, confidence_threshold=confidence_threshold)
    try:
        return engine.run_inference(frame)
    finally:
        engine.release_model()
