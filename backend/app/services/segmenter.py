"""Turns a live transcript stream into 1-minute segments stored in the DB.

Each recording is one `Speech` row (the session). Its `id` is the session ID
shared by every `RealtimeSegment` produced during that recording. Committed
(finalized) transcript text is buffered and flushed to a `RealtimeSegment` once
per minute, with an incrementing `segment_index`.

Gemini is intentionally NOT called here yet — that hooks in later (e.g. set the
segment's `nudge`/feed it to scoring). For now this only persists transcripts.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from sqlmodel import Session

from app.database import engine
from app.models import RealtimeSegment, Speech, User

# One segment per minute of transcribed speech.
SEGMENT_SECONDS = 60

# Until the extension carries a real (Supabase) auth token, segments are owned by
# this stand-in user so the Speech.user_id foreign key is satisfied.
DEMO_USER_ID = "extension-demo-user"
DEMO_USER_NAME = "Extension Demo User"


def _ensure_demo_user(session: Session) -> str:
    if not session.get(User, DEMO_USER_ID):
        session.add(User(id=DEMO_USER_ID, name=DEMO_USER_NAME))
        session.commit()
    return DEMO_USER_ID


class SpeechSegmenter:
    """Accumulates committed transcript text and writes 1-minute segments.

    Usage:
        seg = SpeechSegmenter()          # creates the Speech (session)
        await seg.add_committed(text)    # per finalized transcript
        await seg.force_flush()          # called by a 60s timer
        await seg.flush_remaining()      # on stop, write the tail
        seg.end()                        # mark the Speech finished
    """

    def __init__(self, user_id: str | None = None, segment_seconds: int = SEGMENT_SECONDS):
        self.segment_seconds = segment_seconds
        self._buffer: list[str] = []
        self.segment_index = 0
        self._lock = asyncio.Lock()
        self._window_start = time.monotonic()
        self._window_started_iso = datetime.utcnow().isoformat()

        # Create the session (Speech) row up front.
        with Session(engine) as session:
            uid = user_id or _ensure_demo_user(session)
            speech = Speech(user_id=uid)
            session.add(speech)
            session.commit()
            session.refresh(speech)
            self.speech_id = speech.id

    async def add_committed(self, text: str) -> None:
        """Buffer one finalized (committed) transcript chunk."""
        if text and text.strip():
            async with self._lock:
                self._buffer.append(text.strip())

    async def force_flush(self) -> None:
        """Called every `segment_seconds`: write a segment if we have text."""
        async with self._lock:
            if self._buffer:
                self._write_segment()
            else:
                # A silent minute — keep the 1-minute cadence aligned.
                self._reset_window()

    async def flush_remaining(self) -> None:
        """Write whatever is left when the recording stops."""
        async with self._lock:
            if self._buffer:
                self._write_segment()

    # -- internal (call while holding the lock) --
    def _write_segment(self) -> None:
        transcript = " ".join(self._buffer).strip()
        duration = round(time.monotonic() - self._window_start, 2)
        with Session(engine) as session:
            session.add(
                RealtimeSegment(
                    speech_id=self.speech_id,
                    transcript=transcript,
                    segment_index=self.segment_index,
                    recorded_at=self._window_started_iso,
                    duration_seconds=duration,
                )
            )
            session.commit()
        self.segment_index += 1
        self._reset_window()

    def _reset_window(self) -> None:
        self._buffer = []
        self._window_start = time.monotonic()
        self._window_started_iso = datetime.utcnow().isoformat()

    def end(self) -> None:
        """Mark the session finished."""
        with Session(engine) as session:
            speech = session.get(Speech, self.speech_id)
            if speech:
                speech.ended_at = datetime.utcnow().isoformat()
                speech.status = "done"
                session.add(speech)
                session.commit()
