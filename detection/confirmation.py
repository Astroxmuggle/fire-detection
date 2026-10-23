"""Temporal confirmation of repeated detections.

The tracker works per class so a scene that contains fire *and* smoke can
confirm both, and so that one class disappearing never resets the other.

Lifecycle of a class:

* every frame the class is present increments its streak,
* reaching ``required_frames`` raises the alarm **once** and latches the class,
* while latched no further events are produced,
* the class re-arms only after ``release_frames`` consecutive frames without it
  (and only after ``cooldown_seconds`` have elapsed).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

_DEFAULT_NAMES = {0: "fire", 1: "smoke"}


@dataclass
class _ClassState:
    streak: int = 0
    missing: int = 0
    latched: bool = False
    last_confirmed_at: Optional[float] = None


class ConfirmationTracker:
    """Track repeated detections across consecutive frames, per class."""

    def __init__(
        self,
        required_frames: int = 2,
        release_frames: int = 3,
        cooldown_seconds: float = 0.0,
        clock=time.monotonic,
    ):
        self.required_frames = max(1, int(required_frames))
        self.release_frames = max(1, int(release_frames))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._clock = clock
        self._states: Dict[str, _ClassState] = {}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def class_name(detection) -> Optional[str]:
        """Return the lower-case class name for a detection dict, if any."""
        if not isinstance(detection, dict):
            return None
        for key in ("class_name", "label", "name"):
            value = detection.get(key)
            if value not in (None, ""):
                return str(value).lower()

        class_id = detection.get("class_id")
        if class_id is not None:
            try:
                return _DEFAULT_NAMES.get(int(class_id), str(class_id))
            except (TypeError, ValueError):
                return str(class_id)
        return None

    @staticmethod
    def _confidence(detection) -> float:
        try:
            return float(detection.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0

    # -------------------------------------------------------------------- core
    def update_frame(self, detections: Optional[Iterable[dict]], now: Optional[float] = None) -> List[dict]:
        """Advance the state machine by one frame.

        Returns the detections that became confirmed on this frame. A class
        that stays visible after confirming is *not* reported again.
        """
        now = self._clock() if now is None else float(now)

        best_per_class: Dict[str, dict] = {}
        for detection in detections or []:
            name = self.class_name(detection)
            if not name:
                continue
            current = best_per_class.get(name)
            if current is None or self._confidence(detection) > self._confidence(current):
                best_per_class[name] = detection

        confirmed: List[dict] = []
        for name, detection in best_per_class.items():
            state = self._states.setdefault(name, _ClassState())
            state.streak += 1
            state.missing = 0

            if state.latched:
                continue

            if state.streak < self.required_frames:
                continue

            if (
                state.last_confirmed_at is not None
                and self.cooldown_seconds > 0
                and (now - state.last_confirmed_at) < self.cooldown_seconds
            ):
                continue

            state.latched = True
            state.last_confirmed_at = now
            confirmed.append(detection)

        for name in list(self._states.keys()):
            if name in best_per_class:
                continue
            state = self._states[name]
            state.streak = 0
            state.missing += 1
            if state.missing >= self.release_frames:
                state.latched = False

        return confirmed

    def update(self, detection: Optional[dict], now: Optional[float] = None) -> bool:
        """Convenience wrapper for single-detection callers."""
        return bool(self.update_frame([] if detection is None else [detection], now=now))

    def reset(self) -> None:
        self._states.clear()

    @property
    def confirmed_classes(self) -> set:
        return {name for name, state in self._states.items() if state.latched}

    def snapshot(self) -> Dict[str, dict]:
        """Expose the internal state (used by tests and the status endpoint)."""
        return {
            name: {
                "streak": state.streak,
                "missing": state.missing,
                "latched": state.latched,
            }
            for name, state in self._states.items()
        }
