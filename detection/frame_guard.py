"""Cheap frame-quality guards run before the neural network.

A covered lens, a dark room or a uniform wall produces featureless frames on
which small detectors are known to hallucinate. Detecting that condition costs
one grayscale conversion instead of a full inference pass, and it removes the
entire class of "blank wall raises a fire alarm" failures.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


def frame_detail_score(frame) -> float:
    """Return the standard deviation of the grayscale frame (0 = uniform)."""
    if frame is None:
        return 0.0

    try:
        array = np.asarray(frame)
    except Exception:  # noqa: BLE001 - defensive, frame types vary
        return 0.0

    if array.size == 0:
        return 0.0

    if array.ndim == 3:
        gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY) if array.shape[2] >= 3 else array[:, :, 0]
    else:
        gray = array

    return float(np.std(gray))


def is_informative_frame(frame, min_std: float = 6.0) -> bool:
    """True when the frame carries enough visual detail to be worth analysing."""
    return frame_detail_score(frame) >= float(min_std)


def describe_frame(frame, min_std: float = 6.0) -> dict:
    """Structured diagnostic used by the status endpoint and tests."""
    score = frame_detail_score(frame)
    return {
        "detail_score": round(score, 3),
        "min_std": float(min_std),
        "informative": score >= float(min_std),
    }


def annotate_skipped_frame(frame, score: Optional[float] = None):
    """Return a copy of *frame* marked as skipped by the quality guard."""
    if frame is None:
        return frame

    annotated = frame.copy()
    height, width = annotated.shape[:2]
    label = "LOW DETAIL - INFERENCE SKIPPED"
    if score is not None:
        label = f"{label} (std {score:.1f})"

    cv2.rectangle(annotated, (0, 0), (width, 28), (30, 30, 30), -1)
    cv2.putText(
        annotated,
        label,
        (8, 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 200, 255),
        1,
        cv2.LINE_AA,
    )
    return annotated
