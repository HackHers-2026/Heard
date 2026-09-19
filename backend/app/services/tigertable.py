"""TigerData analytics — inserts events into TimescaleDB hypertables.

No-op stub when TIGERDATA_URL is unset — never crashes local dev or tests.
Connection is created once per process and reused.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

_TIGERDATA_URL = os.getenv("TIGERDATA_URL", "")

# In-process mirror — always populated, used when no DB connection
_local: list[dict] = []

_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        try:
            import psycopg2
            _conn = psycopg2.connect(_TIGERDATA_URL)
            _conn.autocommit = True
        except Exception:
            _conn = None
    return _conn


def track(event: str, payload: dict) -> None:
    """Insert one analytics event. Silently drops on any error."""
    now = datetime.now(timezone.utc)
    _local.append({"event": event, "time": now.isoformat(), **payload})

    if not _TIGERDATA_URL:
        return

    try:
        conn = _get_conn()
        if conn is None:
            return
        with conn.cursor() as cur:
            if event == "speech.ended":
                cur.execute(
                    """INSERT INTO speech_events
                       (time, user_id, speech_id, overall, clarity, volume, pace, confidence, structure)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (now, payload.get("user_id"), payload.get("speech_id"),
                     payload.get("overall"), payload.get("clarity"), payload.get("volume"),
                     payload.get("pace"), payload.get("confidence"), payload.get("structure")),
                )
            elif event == "segment.posted":
                cur.execute(
                    """INSERT INTO segment_events (time, speech_id, pace_wpm, avg_volume)
                       VALUES (%s, %s, %s, %s)""",
                    (now, payload.get("speech_id"),
                     payload.get("pace_wpm"), payload.get("avg_volume")),
                )
            elif event == "post.liked":
                cur.execute(
                    """INSERT INTO post_likes (time, post_id, user_id, career_tag)
                       VALUES (%s, %s, %s, %s)""",
                    (now, payload.get("post_id"),
                     payload.get("user_id"), payload.get("career_tag")),
                )
    except Exception:
        pass  # analytics must never break the main flow


def local_events() -> list[dict]:
    """In-process mirror — available with or without a DB connection."""
    return _local
