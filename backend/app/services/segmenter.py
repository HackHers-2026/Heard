"""Turns a live transcript stream into 1-minute segments stored in the DB.

Each recording is one `Speech` row (the session). Its `id` is the session ID
shared by every `RealtimeSegment` produced during that recording. Committed
(finalized) transcript text is buffered and flushed to a `RealtimeSegment` once
per minute, with an incrementing `segment_index`.

After each segment is persisted the segmenter invokes an optional async
`on_segment(segment_id, transcript, segment_index)` callback — the coaching
worker uses this to enqueue the minute for Backboard/Gemini analysis without
blocking transcription.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Awaitable, Callable, Optional

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

    # async callback(segment_id, transcript, segment_index) fired after each
    # segment is persisted; set by the caller (e.g. the coaching worker).
    OnSegment = Callable[[str, str, int], Awaitable[None]]

    def __init__(self, user_id: str | None = None, segment_seconds: int = SEGMENT_SECONDS):
        self.segment_seconds = segment_seconds
        self._buffer: list[str] = []
        self.segment_index = 0
        self._lock = asyncio.Lock()
        self._window_start = time.monotonic()
        self._window_started_iso = datetime.utcnow().isoformat()
        self.on_segment: Optional["SpeechSegmenter.OnSegment"] = None

        # Create the session (Speech) row up front.
        with Session(engine) as session:
            uid = user_id or _ensure_demo_user(session)
            speech = Speech(user_id=uid)
            session.add(speech)
            session.commit()
            session.refresh(speech)
            self.speech_id = speech.id
            self.user_id = uid

    async def add_committed(self, text: str) -> None:
        """Buffer one finalized (committed) transcript chunk."""
        if text and text.strip():
            async with self._lock:
                self._buffer.append(text.strip())

    async def force_flush(self) -> None:
        """Called every `segment_seconds`: write a segment if we have text."""
        info = None
        async with self._lock:
            if self._buffer:
                info = self._write_segment()
            else:
                # A silent minute — keep the 1-minute cadence aligned.
                self._reset_window()
        await self._notify(info)

    async def flush_remaining(self) -> None:
        """Write whatever is left when the recording stops."""
        info = None
        async with self._lock:
            if self._buffer:
                info = self._write_segment()
        await self._notify(info)

    async def _notify(self, info: tuple[str, str, int] | None) -> None:
        """Hand a freshly persisted segment to the coaching callback, if set.
        Runs outside the lock so slow AI work never stalls transcription."""
        if info and self.on_segment:
            await self.on_segment(*info)

    # -- internal (call while holding the lock) --
    def _write_segment(self) -> tuple[str, str, int]:
        """Persist the buffered minute; return (segment_id, transcript, index)."""
        transcript = " ".join(self._buffer).strip()
        duration = round(time.monotonic() - self._window_start, 2)
        index = self.segment_index
        with Session(engine) as session:
            segment = RealtimeSegment(
                speech_id=self.speech_id,
                transcript=transcript,
                segment_index=index,
                recorded_at=self._window_started_iso,
                duration_seconds=duration,
            )
            session.add(segment)
            session.commit()
            session.refresh(segment)
            segment_id = segment.id
        self.segment_index += 1
        self._reset_window()
        return segment_id, transcript, index

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
