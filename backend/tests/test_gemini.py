import os
os.environ.pop("GEMINI_API_KEY", None)   # force stub mode for all tests

import pytest
from sqlmodel import create_engine, Session, SQLModel
from app.models import Speech, RealtimeSegment, SpeechMetrics
from app.services.gemini import encourage, nudge, score

# ── in-memory DB fixture for score() tests ────────────────────────────────────

_engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(_engine)


@pytest.fixture
def tmp_db_session():
    with Session(_engine) as s:
        from uuid import uuid4
        user_id = str(uuid4())

        # create a minimal User row so FK constraint is satisfied
        from app.models import User
        u = User(id=user_id, name="test")
        s.add(u); s.commit()

        sp = Speech(user_id=user_id)
        s.add(sp); s.commit(); s.refresh(sp)

        seg = RealtimeSegment(
            speech_id=sp.id,
            transcript="Hello everyone, um, I think we should uh consider this proposal.",
            segment_index=0,
            recorded_at="2026-01-01T00:00:00",
            duration_seconds=60.0,
            avg_volume=65,
            volume_variance=5,
        )
        s.add(seg); s.commit()

        def get_metrics():
            return s.get(SpeechMetrics, s.exec(
                __import__("sqlmodel").select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)
            ).first().id if s.exec(
                __import__("sqlmodel").select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)
            ).first() else None)

        # simpler helper
        def _get_metrics():
            from sqlmodel import select
            return s.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)).first()

        yield {"speech_id": sp.id, "session": s, "get_metrics": _get_metrics}


# ── encourage ─────────────────────────────────────────────────────────────────

def test_encourage_quick_stub():
    result = encourage("quick", None)
    assert "message" in result
    assert isinstance(result["message"], str)
    assert "outline" not in result


def test_encourage_plan_stub_has_outline():
    result = encourage("plan", "pitch to investors")
    assert "outline" in result
    assert isinstance(result["outline"], list)
    assert len(result["outline"]) > 0


# ── nudge ─────────────────────────────────────────────────────────────────────

def test_nudge_returns_short_string_or_none():
    result = nudge("hello world um yeah so basically", avg_volume=60, pace_wpm=90)
    assert result is None or (isinstance(result, str) and len(result.split()) <= 10)


def test_nudge_stub_never_raises():
    result = nudge("", avg_volume=0, pace_wpm=0)
    assert result is None or isinstance(result, str)


# ── score ─────────────────────────────────────────────────────────────────────

def test_score_stub_saves_metrics(tmp_db_session):
    score(tmp_db_session["speech_id"], tmp_db_session["session"])
    metrics = tmp_db_session["get_metrics"]()
    assert metrics is not None
    assert 0 <= metrics.overall <= 100
    assert metrics.summary != ""


def test_score_sets_speech_status_done(tmp_db_session):
    score(tmp_db_session["speech_id"], tmp_db_session["session"])
    from sqlmodel import select
    speech = tmp_db_session["session"].get(Speech, tmp_db_session["speech_id"])
    assert speech.status == "done"


def test_score_idempotent(tmp_db_session):
    score(tmp_db_session["speech_id"], tmp_db_session["session"])
    score(tmp_db_session["speech_id"], tmp_db_session["session"])  # second call is no-op
    from sqlmodel import select
    all_metrics = tmp_db_session["session"].exec(
        select(SpeechMetrics).where(SpeechMetrics.speech_id == tmp_db_session["speech_id"])
    ).all()
    assert len(all_metrics) == 1
