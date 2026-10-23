"""In-process event bus backing Server-Sent Events.

Design constraints:

* **Never block the producer.** Publishing does a non-blocking offer to each
  subscriber; camera capture, inference and database writes must not wait for a
  browser.
* **Bounded memory.** Each subscriber has a fixed-size queue and the bus keeps a
  bounded replay buffer.
* **Explicit slow-consumer handling.** When a subscriber's queue is full the
  oldest event is dropped and the subscriber is marked lagged; the SSE generator
  turns that into a ``resync`` event telling the client to refresh authoritative
  state from the database.
* **No durability claim.** This is a notification mechanism. Persisted incidents
  and events remain the source of truth, and replay is best-effort inside the
  process that produced the events.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

from config import Config


class BusFull(RuntimeError):
    """The maximum number of concurrent subscribers has been reached."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Event:
    id: int
    type: str
    ts: str
    payload: Dict[str, Any]

    def envelope(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "timestamp": self.ts, "payload": self.payload}

    def to_sse(self) -> str:
        data = json.dumps(self.envelope(), default=str, separators=(",", ":"), ensure_ascii=False)
        return f"id: {self.id}\nevent: {self.type}\ndata: {data}\n\n"


class Subscription:
    """One connected SSE client."""

    def __init__(self, maxsize: int):
        self._queue: "queue.Queue[Event]" = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self.dropped = 0
        self._lagged = False
        self.closed = False

    # ------------------------------------------------------------------ produce
    def offer(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
            return
        except queue.Full:
            pass

        # Drop the oldest event, keep the newest, and remember the lag.
        try:
            self._queue.get_nowait()
        except queue.Empty:  # pragma: no cover - race with the consumer
            pass
        with self._lock:
            self.dropped += 1
            self._lagged = True
        try:
            self._queue.put_nowait(event)
        except queue.Full:  # pragma: no cover - race with the consumer
            with self._lock:
                self.dropped += 1

    # ------------------------------------------------------------------ consume
    def get(self, timeout: float) -> Optional[Event]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def consume_lag(self) -> int:
        """Return the number of dropped events since the last call, then reset."""
        with self._lock:
            if not self._lagged:
                return 0
            self._lagged = False
            return self.dropped

    def close(self) -> None:
        self.closed = True

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize


class EventBus:
    def __init__(self, history_size: int = 256, queue_size: int = 100, max_subscribers: int = 16):
        self._lock = threading.Lock()
        self._next_id = 0
        self._history: Deque[Event] = deque(maxlen=max(1, int(history_size)))
        self._subscribers: List[Subscription] = []
        self.queue_size = max(1, int(queue_size))
        self.max_subscribers = max(1, int(max_subscribers))

    # ---------------------------------------------------------------- lifecycle
    def subscribe(self) -> Subscription:
        with self._lock:
            if len(self._subscribers) >= self.max_subscribers:
                raise BusFull(
                    f"maximum of {self.max_subscribers} concurrent SSE subscribers reached"
                )
            subscription = Subscription(self.queue_size)
            self._subscribers.append(subscription)
            return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            if subscription in self._subscribers:
                self._subscribers.remove(subscription)
        subscription.close()

    # ------------------------------------------------------------------- publish
    def publish(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Event:
        with self._lock:
            self._next_id += 1
            event = Event(
                id=self._next_id,
                type=str(event_type),
                ts=_utc_now(),
                payload=dict(payload or {}),
            )
            self._history.append(event)
            subscribers = list(self._subscribers)

        for subscription in subscribers:
            if not subscription.closed:
                subscription.offer(event)
        return event

    # -------------------------------------------------------------------- replay
    def replay_since(self, last_event_id: int) -> Tuple[List[Event], bool]:
        """Events after *last_event_id*; ``gap`` is True when continuity is lost."""
        with self._lock:
            if not self._history:
                return [], False

            latest = self._history[-1].id
            oldest = self._history[0].id

            if last_event_id > latest:
                # The client saw ids from a previous process: the server restarted
                # and its counter went backwards.
                return [], True
            if last_event_id < oldest - 1:
                return [], True
            return [event for event in self._history if event.id > last_event_id], False

    # --------------------------------------------------------------------- stats
    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def latest_id(self) -> int:
        with self._lock:
            return self._next_id

    def reset_for_tests(self) -> None:
        with self._lock:
            self._next_id = 0
            self._history.clear()
            for subscription in self._subscribers:
                subscription.close()
            self._subscribers.clear()


def _build_default_bus() -> EventBus:
    return EventBus(
        history_size=Config.SSE_REPLAY_BUFFER,
        queue_size=Config.SSE_QUEUE_SIZE,
        max_subscribers=Config.SSE_MAX_SUBSCRIBERS,
    )


_BUS = _build_default_bus()


def get_bus() -> EventBus:
    return _BUS


def set_bus(bus: EventBus) -> None:
    """Replace the process-wide bus (tests)."""
    global _BUS
    _BUS = bus


def reset_bus() -> None:
    """Fresh bus with the configured limits (tests and restarts)."""
    global _BUS
    _BUS = _build_default_bus()


def publish(event_type: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Event]:
    """Publish without ever raising into the detection path."""
    try:
        return get_bus().publish(event_type, payload)
    except Exception:  # noqa: BLE001 - notifications must never break capture
        return None
