"""Ultralytics YOLO implementation of the model adapter.

This wraps the *existing* inference call and the *existing* output conversion.
Nothing here changes thresholds, image size or post-processing; it is a move of
code that used to live inside ``services.camera_service``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from adapters.model.base import ModelAdapter, ModelInfo, Prediction
from config import Config


def _to_detections(results) -> List[Dict[str, Any]]:
    """Convert Ultralytics results to the normalised detection shape.

    Behavioural contract, kept identical to the pre-adapter implementation:
    confidences and class ids are read from ``boxes``, class names come from
    ``results[0].names`` and are lower-cased.
    """
    if not results or len(results) == 0 or results[0].boxes is None:
        return []

    names = getattr(results[0], "names", {}) or {}
    detections: List[Dict[str, Any]] = []
    for box in results[0].boxes:
        confidence = float(box.conf[0]) if hasattr(box.conf, "__len__") else float(box.conf)
        class_id = int(box.cls[0]) if hasattr(box.cls, "__len__") else int(box.cls)
        detections.append({
            "class_name": str(names.get(class_id, class_id)).lower(),
            "class_id": class_id,
            "confidence": confidence,
            "bbox": box.xyxy[0].tolist(),
        })
    return detections


def _plot(results, frame):
    """Draw the model's overlays; never let rendering break the pipeline."""
    try:
        return results[0].plot()
    except Exception:  # noqa: BLE001 - plotting is cosmetic
        return frame


class YoloModelAdapter(ModelAdapter):
    """YOLO checkpoint behind the model-adapter protocol."""

    def __init__(self, model_path: Optional[str] = None, confidence_threshold: Optional[float] = None):
        self.model_path = str(model_path or Config.MODEL_PATH)
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Model not found at {self.model_path}")

        # Imported lazily: the adapter module stays importable (and testable)
        # without paying the torch import cost.
        from ultralytics import YOLO

        self.confidence_threshold = float(
            Config.CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold
        )
        self._model = YOLO(self.model_path)
        names = getattr(self._model, "names", {}) or {}
        self._info = ModelInfo(
            name="yolo11",
            path=self.model_path,
            task=str(getattr(self._model, "task", "detect") or "detect"),
            classes={int(key): str(value) for key, value in names.items()},
        )

    def info(self) -> ModelInfo:
        return self._info

    def predict(self, frame) -> Prediction:
        if frame is None:
            return Prediction(detections=[], annotated=None)

        results = self._model(
            frame,
            conf=self.confidence_threshold,
            imgsz=640,
            verbose=False,
        )
        return Prediction(
            detections=_to_detections(results),
            annotated=_plot(results, frame),
        )

    def close(self) -> None:
        self._model = None
