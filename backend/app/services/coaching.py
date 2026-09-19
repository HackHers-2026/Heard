"""Per-session coaching worker.

The realtime transcription pipeline must never block while Gemini/Backboard
think. Each practice session gets ONE worker draining an asyncio.Queue:

                 ┌→ DB save (segmenter)
  Transcript ────┤
                 └→ asyncio Queue → AI worker → Backboard → Gemini
                                        ↓
                                    feedback → DB (segment.nudge + feedback_json)
                                        ↓
                                    WebSocket → Chrome sidebar

Exactly one worker per session guarantees minute 1 → 2 → 3 reach the Backboard
thread *in order*, even if one request is slower than another (unlike firing
independent asyncio tasks per segment).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import RealtimeSegment, Speech
from app.services import backboard

logger = logging.getLogger("heard.coaching")

# Sentinel that tells the worker loop to stop.
_STOP = object()

SendFn = Callable[[dict], Awaitable[None]]


class CoachingWorker:
    """Owns one session's ordered coaching queue + Backboard thread state."""

    def __init__(self, user_id: str, speech_id: str, send: Optional[SendFn] = None):
        self.user_id = user_id
        self.speech_id = speech_id
        self.send = send                     # push coaching frames to the client, or None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.assistant_id: str | None = None
        self.thread_id: str | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Resolve the user's coach assistant + any existing session thread,
        then spin up the single background worker."""
        try:
            self.assistant_id = await backboard.ensure_assistant(self.user_id)
        except Exception:
            logger.exception("ensure_assistant failed; coaching runs in stub mode")
            self.assistant_id = None

        with Session(engine) as session:
            speech = session.get(Speech, self.speech_id)
            self.thread_id = speech.backboard_thread_id if speech else None

        self._task = asyncio.create_task(self._run())

    async def enqueue(self, segment_id: str, transcript: str, segment_index: int) -> None:
        """Non-blocking hand-off from the segmenter (segmenter.on_segment)."""
        await self.queue.put((segment_id, transcript, segment_index))

    async def _run(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is _STOP:
                    break
                await self._process(*item)
            except Exception:
                logger.exception("coaching worker error")
            finally:
                self.queue.task_done()

    async def _process(self, segment_id: str, transcript: str, segment_index: int) -> None:
        feedback, thread_id = await backboard.coach_segment(
            self.user_id, self.assistant_id, self.thread_id, transcript, segment_index
        )

        # Persist the thread id the first time Backboard mints it for this session.
        if thread_id and thread_id != self.thread_id:
            self.thread_id = thread_id
            self._persist_thread_id(thread_id)

        self._save_feedback(segment_id, feedback)

        if self.send is not None:
            try:
                await self.send({
                    "type": "coaching",
                    "segment_index": segment_index,
                    **feedback,
                })
            except Exception:
                pass  # a closed socket must never break coaching

    async def finalize(self) -> None:
        """Drain outstanding segments, stop the worker, then extract durable
        memories from the completed session (memory="Auto")."""
        if self._task is None:
            return
        await self.queue.join()          # wait for every enqueued segment
        await self.queue.put(_STOP)
        await self._task

        summary = self._build_session_summary()
        try:
            await backboard.finalize_session(self.assistant_id, self.thread_id, summary)
        except Exception:
            logger.exception("finalize_session failed")

    # -- DB helpers -----------------------------------------------------------
    def _persist_thread_id(self, thread_id: str) -> None:
        with Session(engine) as session:
            speech = session.get(Speech, self.speech_id)
            if speech and not speech.backboard_thread_id:
                speech.backboard_thread_id = thread_id
                session.add(speech)
                session.commit()

    def _save_feedback(self, segment_id: str, feedback: dict) -> None:
        with Session(engine) as session:
            seg = session.get(RealtimeSegment, segment_id)
            if seg:
                seg.nudge = feedback.get("nudge", "") or seg.nudge
                seg.feedback_json = json.dumps(feedback)
                session.add(seg)
                session.commit()

    def _build_session_summary(self) -> str:
        """Assemble a compact end-of-session summary from stored feedback so
        Backboard can extract durable coaching memories."""
        with Session(engine) as session:
            segs = session.exec(
                select(RealtimeSegment)
                .where(RealtimeSegment.speech_id == self.speech_id)
                .order_by(RealtimeSegment.segment_index)
            ).all()

        minutes = len(segs)
        focus_areas: list[str] = []
        goals: list[str] = []
        for s in segs:
            try:
                fb = json.loads(s.feedback_json or "{}")
            except (json.JSONDecodeError, ValueError):
                fb = {}
            if fb.get("focus_area"):
                focus_areas.append(fb["focus_area"])
            if fb.get("next_minute_goal"):
                goals.append(fb["next_minute_goal"])

        recurring = _top(focus_areas)
        lines = [
            "SESSION COMPLETE",
            f"Duration: ~{minutes} minute(s) of live practice.",
        ]
        if recurring:
            lines.append("Recurring focus areas this session: " + ", ".join(recurring) + ".")
        if goals:
            lines.append("Coaching goals raised: " + "; ".join(goals[-3:]) + ".")
        lines.append(
            "Update this user's long-term communication profile: capture durable "
            "patterns, improvements vs previous sessions, and the next coaching "
            "priorities. Do not store the raw transcript."
        )
        return "\n".join(lines)


def _top(items: list[str], n: int = 3) -> list[str]:
    counts: dict[str, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]]
