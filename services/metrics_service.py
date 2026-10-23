"""Aggregated runtime metrics, derived from the database plus live counters."""

from __future__ import annotations

import threading
import time

from database.db import get_db_connection
from services.event_service import get_event_stats


class MetricsService:
    def __init__(self):
        self.false_positives = 0
        self.false_negatives = 0
        self.started_at = time.time()
        self._lock = threading.Lock()

    def log_false_positive(self, count: int = 1):
        with self._lock:
            self.false_positives += int(count)

    def log_false_negative(self, count: int = 1):
        with self._lock:
            self.false_negatives += int(count)

    def reset_counters(self):
        with self._lock:
            self.false_positives = 0
            self.false_negatives = 0

    def get_metrics(self) -> dict:
        stats = get_event_stats()

        connection = get_db_connection()
        try:
            alerts_total = connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            alerts_pending = connection.execute(
                "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0"
            ).fetchone()[0]
        finally:
            connection.close()

        with self._lock:
            false_positives = self.false_positives
            false_negatives = self.false_negatives

        return {
            "detection_count": stats["detection_count"],
            "confirmed_incidents": stats["confirmed_incidents"],
            "pending_incidents": stats["pending_incidents"],
            "by_class": stats["by_class"],
            "last_event_at": stats["last_event_at"],
            "alerts_total": alerts_total,
            "alerts_pending": alerts_pending,
            "alerts_acknowledged": alerts_total - alerts_pending,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "uptime_seconds": round(time.time() - self.started_at, 1),
        }


_METRICS = MetricsService()


def get_metrics_service() -> MetricsService:
    return _METRICS


def get_metrics() -> dict:
    return _METRICS.get_metrics()
