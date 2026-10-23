"""Detection orchestration: normalise, filter, suppress, sanity-check, confirm."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from config import Config
from detection.confirmation import ConfirmationTracker
from detection.postprocess import filter_detections, flatten_bbox, non_max_suppression

_CLASS_ID_NAMES = {0: "fire", 1: "smoke"}


class DetectionManager:
    """Turn raw model output into confirmed incidents.

    Per-class confidence thresholds are authoritative; ``confidence_threshold``
    is only the fallback for classes without an explicit entry.
    """

    def __init__(
        self,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        required_frames: Optional[int] = None,
        release_frames: Optional[int] = None,
        cooldown_seconds: Optional[float] = None,
        class_thresholds: Optional[Dict[str, float]] = None,
        min_box_area_ratio: Optional[float] = None,
        max_box_area_ratio: Optional[float] = None,
    ):
        self.confidence_threshold = float(
            Config.CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold
        )
        self.iou_threshold = float(Config.IOU_THRESHOLD if iou_threshold is None else iou_threshold)
        self.class_thresholds = (
            dict(class_thresholds)
            if class_thresholds is not None
            else {
                "fire": float(Config.FIRE_CONFIDENCE_THRESHOLD),
                "smoke": float(Config.SMOKE_CONFIDENCE_THRESHOLD),
            }
        )
        self.min_box_area_ratio = float(
            Config.MIN_BOX_AREA_RATIO if min_box_area_ratio is None else min_box_area_ratio
        )
        self.max_box_area_ratio = float(
            Config.MAX_BOX_AREA_RATIO if max_box_area_ratio is None else max_box_area_ratio
        )
        self.confirmation = ConfirmationTracker(
            required_frames=Config.CONFIRMATION_FRAMES if required_frames is None else required_frames,
            release_frames=Config.CONFIRMATION_RELEASE_FRAMES if release_frames is None else release_frames,
            cooldown_seconds=Config.CONFIRMATION_COOLDOWN if cooldown_seconds is None else cooldown_seconds,
        )

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _normalize_detection(detection) -> Optional[Dict]:
        if not isinstance(detection, dict):
            return None

        class_name = detection.get("class_name") or detection.get("label") or detection.get("name")
        if class_name in (None, ""):
            class_id = detection.get("class_id")
            try:
                class_name = _CLASS_ID_NAMES.get(int(class_id), None) if class_id is not None else None
            except (TypeError, ValueError):
                class_name = None
        if class_name in (None, ""):
            class_name = "unknown"

        try:
            confidence = float(detection.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        bbox = flatten_bbox(detection.get("bbox", detection.get("box")))

        return {
            "class_name": str(class_name).lower(),
            "confidence": confidence,
            "bbox": bbox,
        }

    def _box_is_plausible(self, detection: Dict, frame_shape: Optional[Sequence[int]]) -> bool:
        if not frame_shape or len(frame_shape) < 2:
            return True

        bbox = detection.get("bbox")
        if bbox is None:
            return True

        frame_area = float(frame_shape[0]) * float(frame_shape[1])
        if frame_area <= 0:
            return True

        area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
        ratio = area / frame_area
        return self.min_box_area_ratio <= ratio <= self.max_box_area_ratio

    # ------------------------------------------------------------------- main
    def process_detections(
        self,
        detections: Optional[List[Dict]],
        frame_shape: Optional[Sequence[int]] = None,
        now: Optional[float] = None,
    ) -> List[Dict]:
        normalized = [
            item
            for item in (self._normalize_detection(detection) for detection in (detections or []))
            if item is not None
        ]

        if not normalized:
            # Still advance the state machine so absent classes can decay.
            self.confirmation.update_frame([], now=now)
            return []

        filtered = filter_detections(normalized, self.confidence_threshold, self.class_thresholds)
        final = non_max_suppression(filtered, iou_threshold=self.iou_threshold)
        final = [item for item in final if self._box_is_plausible(item, frame_shape)]

        confirmed = self.confirmation.update_frame(final, now=now)
        return [{**item, "confirmed": True} for item in confirmed]

    def reset(self) -> None:
        self.confirmation.reset()
