"""Alert persistence, acknowledgement and audible notification."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from config import Config
from database.db import get_db_connection


class AlertManager:
    """Create alert records and play a notification sound with a cool-down."""

    def __init__(self, alert_cooldown=60, sound_enabled=None):
        self.alert_cooldown = max(0, int(alert_cooldown))
        self.sound_enabled = bool(Config.ALERT_SOUND_ENABLED if sound_enabled is None else sound_enabled)
        self.last_alert_time = None
        self._alert_records = {}

    # ------------------------------------------------------------------ record
    def create_alert(self, event_id=None, alert_level="info", alert_type=None, acknowledged=False):
        alert_level_name = str(alert_level or alert_type or "info").lower()

        connection = get_db_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO alerts (event_id, alert_level, acknowledged, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(event_id) if event_id is not None else 0,
                    alert_level_name,
                    1 if acknowledged else 0,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
            alert_id = cursor.lastrowid
        finally:
            connection.close()

        record = {
            "id": alert_id,
            "event_id": int(event_id) if event_id is not None else 0,
            "alert_level": alert_level_name,
            "alert_type": str(alert_type or alert_level_name).lower(),
            "acknowledged": bool(acknowledged),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "acknowledged" if acknowledged else "pending",
        }
        self._alert_records[alert_id] = record
        try:
            from services.event_bus import publish
            publish("alert", record)
        except Exception:
            pass
        return record

    # ------------------------------------------------------------------- sound
    def notify(self, alert_type) -> bool:
        """Play the notification sound if the cool-down window has elapsed."""
        current_time = datetime.now(timezone.utc)
        if not self.can_trigger_alert(current_time):
            return False

        self.last_alert_time = current_time
        return self.play_sound(alert_type)

    def trigger_alert(self, alert_type, event_id=None, alert_level=None) -> bool:
        """Cool-down gated alert creation (kept for compatibility)."""
        current_time = datetime.now(timezone.utc)
        if not self.can_trigger_alert(current_time):
            return False

        alert_kind = str(alert_level or alert_type or "info").lower()
        self.last_alert_time = current_time
        self.play_sound(alert_type)
        self.create_alert(event_id=event_id, alert_level=alert_kind, alert_type=alert_type)
        return True

    def can_trigger_alert(self, current_time) -> bool:
        if self.last_alert_time is None:
            return True
        return (current_time - self.last_alert_time).total_seconds() >= self.alert_cooldown

    def play_sound(self, alert_type) -> bool:
        if not self.sound_enabled:
            return False

        sound_file = self.get_sound_file(alert_type)
        if sound_file and os.path.exists(sound_file):
            try:
                import winsound

                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception:  # noqa: BLE001 - optional Windows API
                pass

        try:
            import winsound

            winsound.Beep(1200, 200)
            return True
        except Exception:  # noqa: BLE001 - not on Windows / no audio device
            return False

    def get_sound_file(self, alert_type):
        sound_files = {
            "fire": os.path.join("alerts", "fire_alert.wav"),
            "smoke": os.path.join("alerts", "smoke_alert.wav"),
        }
        return sound_files.get(str(alert_type).lower())


def get_alerts(limit=None):
    connection = get_db_connection()
    try:
        query = "SELECT * FROM alerts ORDER BY created_at DESC, id DESC"
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (int(limit),)
        rows = [dict(row) for row in connection.execute(query, params).fetchall()]
    finally:
        connection.close()

    for item in rows:
        item["status"] = "acknowledged" if item.get("acknowledged") else "pending"
    return rows


def get_alerts_for_event(event_id):
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM alerts WHERE event_id = ? ORDER BY created_at DESC, id DESC",
            (int(event_id),),
        ).fetchall()
    finally:
        connection.close()

    alerts = [dict(row) for row in rows]
    for item in alerts:
        item["status"] = "acknowledged" if item.get("acknowledged") else "pending"
    return alerts


def acknowledge_alert(alert_id) -> bool:
    """Mark an alert acknowledged. Returns False when the id does not exist."""
    if alert_id is None:
        return False

    connection = get_db_connection()
    try:
        existing = connection.execute("SELECT id FROM alerts WHERE id = ?", (int(alert_id),)).fetchone()
        if existing is None:
            return False
        connection.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE id = ?",
            (int(alert_id),),
        )
        connection.commit()
    finally:
        connection.close()
    return True


def acknowledge_alerts_for_event(event_id) -> int:
    """Acknowledge every alert attached to an event. Returns the row count."""
    if event_id is None:
        return 0

    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE event_id = ? AND acknowledged = 0",
            (int(event_id),),
        )
        connection.commit()
        return cursor.rowcount or 0
    finally:
        connection.close()
