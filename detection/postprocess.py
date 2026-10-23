"""Post-processing helpers: threshold filtering and non-maximum suppression."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

import cv2
import numpy as np


def flatten_bbox(bbox) -> Optional[List[float]]:
    """Return ``[x1, y1, x2, y2]`` from the shapes a model or a test may use."""
    if bbox is None:
        return None

    try:
        array = np.asarray(bbox, dtype=np.float32)
    except (TypeError, ValueError):
        return None

    if array.size != 4:
        return None

    return array.reshape(-1).tolist()


def _threshold_for(detection: dict, default: float, class_thresholds: Optional[dict]) -> float:
    if class_thresholds:
        name = str(detection.get("class_name") or "").lower()
        if name in class_thresholds:
            try:
                return float(class_thresholds[name])
            except (TypeError, ValueError):
                pass
    return float(default)


def filter_detections(detections, confidence_threshold, class_thresholds=None):
    """Keep detections at or above the threshold for their own class."""
    if not detections:
        return []

    filtered = []
    for detection in detections:
        try:
            confidence = float(detection.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if confidence >= _threshold_for(detection, confidence_threshold, class_thresholds):
            filtered.append(detection)
    return filtered


def non_max_suppression(detections, iou_threshold=0.4):
    """Suppress overlapping boxes, keeping the most confident one."""
    if not detections:
        return []

    usable = []
    boxes = []
    for detection in detections:
        box = flatten_bbox(detection.get("bbox"))
        if box is None:
            continue
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        usable.append(detection)
        boxes.append(box)

    if not usable:
        return []

    boxes_array = np.asarray(boxes, dtype=np.float32)
    boxes_xywh = boxes_array.copy()
    boxes_xywh[:, 2:] -= boxes_array[:, :2]
    scores = np.array(
        [float(detection.get("confidence", 0.0)) for detection in usable],
        dtype=np.float32,
    )

    indices = cv2.dnn.NMSBoxes(
        boxes_xywh.tolist(),
        scores.tolist(),
        score_threshold=0.0,
        nms_threshold=float(iou_threshold),
    )

    if indices is None or len(indices) == 0:
        return []

    selected = np.asarray(indices).reshape(-1)
    return [usable[int(index)] for index in selected if int(index) < len(usable)]


def process_detections(detections, confidence_threshold=0.5, iou_threshold=0.4):
    """Stateless convenience pipeline (kept for scripts and notebooks)."""
    filtered = filter_detections(detections, confidence_threshold)
    return non_max_suppression(filtered, iou_threshold)
