"""Model adapter contract.

The rest of the application only knows this protocol: a model can describe
itself and turn a BGR frame into normalised detections plus an annotated frame.
Swapping YOLO for another detector, or a different runtime, means writing one
new adapter — nothing above this layer changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelInfo:
    """Static description of a loaded model."""

    name: str
    path: str
    task: str
    classes: Dict[int, str] = field(default_factory=dict)


@dataclass
class Prediction:
    """Result of one inference pass.

    ``detections`` uses the established normalised shape:

        {"class_name": str, "class_id": int, "confidence": float,
         "bbox": [x1, y1, x2, y2]}

    ``annotated`` is a BGR image with the model's overlays, or ``None`` when the
    adapter cannot draw.
    """

    detections: List[Dict[str, Any]]
    annotated: Any = None


@runtime_checkable
class ModelAdapter(Protocol):
    """Minimal surface required by the inference worker."""

    def info(self) -> ModelInfo:
        ...

    def predict(self, frame) -> Prediction:
        ...

    def close(self) -> None:
        ...
