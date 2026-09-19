"""Backboard coaching layer — stub-mode pipeline (no API key required).

Verifies the no-key fallback end-to-end: a persisted segment flows through the
per-session CoachingWorker and lands back on the RealtimeSegment as a live
`nudge` plus structured `feedback_json`.
"""
import asyncio
import json
import os
from uuid import uuid4

os.environ.pop("BACKBOARD_API_KEY", None)  # force stub mode

from sqlmodel import Session

from app.database import engine
from app.models import RealtimeSegment, Speech, SpeechMetrics, User
from app.services import backboard
from app.services.coaching import CoachingWorker

FEEDBACK_KEYS = {"focus_area", "nudge", "evidence", "progress", "next_minute_goal", "scores"}


def test_stub_mode_disabled_without_key():
    backboard._client.cache_clear()
    assert backboard.enabled() is False


def test_coach_segment_returns_structured_feedback():
    feedback, thread_id = asyncio.run(
        backboard.coach_segment(
            user_id="nobody",
            assistant_id=None,          # stub path
            thread_id=None,
            transcript="Our platform helps women speak up with confidence.",
            segment_index=0,
        )
    )
    assert FEEDBACK_KEYS <= set(feedback)
    assert isinstance(feedback["nudge"], str) and feedback["nudge"]
    assert thread_id is None  # stub never mints a thread


def test_parse_feedback_tolerates_code_fences():
    raw = '```json\n{"focus_area":"clarity","nudge":"Get to the point"}\n```'
    parsed = backboard._parse_feedback(raw, "transcript", 0)
    assert parsed["focus_area"] == "clarity"
    assert parsed["nudge"] == "Get to the point"
    assert FEEDBACK_KEYS <= set(parsed)  # normalised shape


def _make_speech_with_segment() -> tuple[str, str]:
    with Session(engine) as s:
        user_id = str(uuid4())
        s.add(User(id=user_id, name="coach-test"))
        speech = Speech(user_id=user_id)
        s.add(speech)
        s.commit()
        s.refresh(speech)
        seg = RealtimeSegment(
            speech_id=speech.id,
            transcript="So basically um I think we should maybe consider this.",
            segment_index=0,
            recorded_at="2026-01-01T00:00:00",
            duration_seconds=60.0,
        )
        s.add(seg)
        s.commit()
        s.refresh(seg)
        return user_id, speech.id, seg.id


def test_worker_persists_feedback_and_pushes_frame():
    backboard._client.cache_clear()
    user_id, speech_id, seg_id = _make_speech_with_segment()
    sent: list[dict] = []

    # `send` must be awaitable — wrap the list append.
    async def _append(payload):
        sent.append(payload)

    async def scenario():
        worker = CoachingWorker(user_id=user_id, speech_id=speech_id, send=_append)
        await worker.start()
        await worker.enqueue(seg_id, "So basically um I think we should maybe consider this.", 0)
        await worker.finalize()

    asyncio.run(scenario())

    # Feedback landed on the segment.
    with Session(engine) as s:
        seg = s.get(RealtimeSegment, seg_id)
        assert seg.nudge != ""
        fb = json.loads(seg.feedback_json)
        assert FEEDBACK_KEYS <= set(fb)

    # A coaching frame was pushed to the (fake) websocket.
    assert len(sent) == 1
    assert sent[0]["type"] == "coaching"
    assert sent[0]["segment_index"] == 0
    assert sent[0]["nudge"] == json.loads(seg.feedback_json)["nudge"]


def test_get_recent_performance_returns_recent_scores():
    with Session(engine) as s:
        user_id = str(uuid4())
        s.add(User(id=user_id, name="perf-test"))
        speech = Speech(user_id=user_id, status="done")
        s.add(speech)
        s.commit()
        s.refresh(speech)
        s.add(SpeechMetrics(
            speech_id=speech.id, clarity=71, structure=63, confidence=80,
            pace=75, volume=68, overall=71,
        ))
        s.commit()

    result = backboard.get_recent_performance(user_id, limit=5)
    assert "last_5_sessions" in result
    assert result["last_5_sessions"][0]["clarity"] == 71
