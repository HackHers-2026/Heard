"""Heard v3 tests — rich metrics, longitudinal context, Backboard integration.

Backboard/Gemini calls are mocked; no live API is required.
"""
import asyncio
import json
import types
import uuid

import pytest
from sqlmodel import Session

from app.database import engine
from app.services import (
    backboard, ai_coach, analysis, channels as channels_svc,
    sessions as sessions_svc, profiles as profiles_svc,
    context_builder, performance_profiles, progress as progress_svc,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _seed_channels():
    with Session(engine) as s:
        channels_svc.seed_channels(s)
    yield


@pytest.fixture(autouse=True)
def _stub_backboard(monkeypatch):
    # Default: Backboard disabled → deterministic stub analysis.
    monkeypatch.setattr(backboard, "enabled", lambda: False)
    yield


def _mk_user(name="V3 User") -> str:
    uid = f"user-{uuid.uuid4()}"
    with Session(engine) as s:
        profiles_svc.ensure_profile(uid, s, display_name=name, email=f"{uid}@ex.com")
    return uid


def _channel_id(slug="technology") -> str:
    with Session(engine) as s:
        return channels_svc.get_channel(slug, s).id


def _seg(index, transcript, audio=None, start=None, end=None):
    start = index * 60 if start is None else start
    end = start + 60 if end is None else end
    return {
        "segment_index": index,
        "transcript": transcript,
        "start_seconds": start,
        "end_seconds": end,
        "audio_metrics": audio or {},
    }


def _run_session(uid, channel_id, segments, *, complete=True):
    with Session(engine) as s:
        ts, _ = sessions_svc.create_session(uid, channel_id, "t", s)
        for seg in segments:
            sessions_svc.ingest_segment(ts.id, uid, seg, s)
        if complete:
            asyncio.run(sessions_svc.complete_session(ts.id, uid, s))
        return ts.id


FULL_AUDIO = {
    "speaking_duration_seconds": 52.4, "silence_duration_seconds": 7.6, "silence_ratio": 0.126,
    "average_rms": 0.18, "peak_rms": 0.42, "rms_std_dev": 0.037,
    "pitch_mean_hz": 196.4, "pitch_min_hz": 161.2, "pitch_max_hz": 247.8, "pitch_std_dev_hz": 21.3,
    "long_pause_count": 2, "average_pause_ms": 510, "max_pause_ms": 1180,
}


# ─────────────────────────────────────────────────────────────────────────────
# Rich metric storage + derivation
# ─────────────────────────────────────────────────────────────────────────────

def test_stores_pitch_amplitude_pause_metrics():
    uid = _mk_user()
    cid = _channel_id()
    sid = _run_session(uid, cid, [_seg(0, "Good morning, today I will explain the system.", FULL_AUDIO)],
                       complete=False)
    with Session(engine) as s:
        segs = sessions_svc.get_segments(sid, s)
    am = segs[0].audio_metrics
    assert am["pitch_mean_hz"] == 196.4
    assert am["average_rms"] == 0.18
    assert am["max_pause_ms"] == 1180


def test_wpm_uses_speaking_duration_then_falls_back():
    # 10 words, speaking_duration 30s → 20 WPM.
    seg_spk = types.SimpleNamespace(
        segment_index=0, start_seconds=0, end_seconds=60, transcript="one two three four five six seven eight nine ten",
        word_count=10, duration_seconds=60.0, audio_metrics={"speaking_duration_seconds": 30.0})
    ev = analysis.segment_evidence(seg_spk)
    assert ev["wpm"] == 20.0

    # No speaking_duration → falls back to segment duration (60s) → 10 WPM.
    seg_fallback = types.SimpleNamespace(
        segment_index=0, start_seconds=0, end_seconds=60, transcript="one two three four five six seven eight nine ten",
        word_count=10, duration_seconds=60.0, audio_metrics={})
    assert analysis.segment_evidence(seg_fallback)["wpm"] == 10.0


def test_missing_pitch_data_is_none_not_fabricated():
    seg = types.SimpleNamespace(
        segment_index=0, start_seconds=0, end_seconds=60, transcript="hello there",
        word_count=2, duration_seconds=60.0, audio_metrics={"average_rms": 0.2, "rms_std_dev": 0.01})
    ev = analysis.session_evidence([seg])
    assert ev["pitch"]["mean_hz"] is None
    assert ev["volume"]["average_rms"] == 0.2  # amplitude present, pitch absent


def test_missing_audio_metrics_no_volume_score():
    seg = types.SimpleNamespace(
        segment_index=0, start_seconds=0, end_seconds=60,
        transcript="a clear opening, a solid middle, and a strong close",
        word_count=10, duration_seconds=60.0, audio_metrics={})
    ev = analysis.session_evidence([seg])
    assert ev["has_audio_metrics"] is False
    assert ev["volume"]["consistency"] is None
    assert ev["deterministic_scores"]["volume"] is None


def test_conciseness_in_schema_and_feedback():
    assert "conciseness" in analysis.DIMENSIONS
    uid = _mk_user()
    sid = _run_session(uid, _channel_id(),
                       [_seg(0, "We chose Postgres. We chose Postgres because it scales. We chose Postgres.", FULL_AUDIO)])
    with Session(engine) as s:
        fb = sessions_svc.get_feedback(sid, s)
    assert fb.conciseness_score is not None


# ─────────────────────────────────────────────────────────────────────────────
# Longitudinal context + performance memory
# ─────────────────────────────────────────────────────────────────────────────

def test_no_previous_history_completes_cleanly():
    uid = _mk_user()
    sid = _run_session(uid, _channel_id(), [_seg(0, "First ever session, hello everyone.", FULL_AUDIO)])
    with Session(engine) as s:
        ctx = context_builder.build_session_analysis_context(uid, sid, s)
    assert ctx["historical"]["has_history"] is False


def test_historical_context_and_previous_comparison():
    uid = _mk_user()
    cid = _channel_id()
    _run_session(uid, cid, [_seg(0, "Session one, a calm and clear delivery today.", FULL_AUDIO)])
    sid2 = _run_session(uid, cid, [_seg(0, "Session two, again clear and well paced.", FULL_AUDIO)])

    with Session(engine) as s:
        # Build context for a *third* session; history should include 2 prior.
        ctx = context_builder._historical_block(uid, cid, s)
    assert ctx["has_history"] is True
    assert ctx["session_count"] == 2
    assert "previous_scores" in ctx
    assert ctx["previous_overall_score"] is not None


def test_performance_profile_updates_after_completion():
    uid = _mk_user()
    cid = _channel_id()
    _run_session(uid, cid, [_seg(0, "One clear opening statement.", FULL_AUDIO)])
    _run_session(uid, cid, [_seg(0, "Another clear and concise statement.", FULL_AUDIO)])
    with Session(engine) as s:
        profile = performance_profiles.get_profile(uid, cid, s)
    assert profile is not None
    assert profile.completed_sessions == 2
    assert profile.improvement_percent is not None  # >=2 sessions


def test_channel_specific_history_isolation():
    uid = _mk_user()
    tech = _channel_id("technology")
    fin = _channel_id("finance")
    _run_session(uid, tech, [_seg(0, "Tech session one.", FULL_AUDIO)])
    _run_session(uid, tech, [_seg(0, "Tech session two.", FULL_AUDIO)])
    _run_session(uid, fin, [_seg(0, "Finance session one.", FULL_AUDIO)])

    with Session(engine) as s:
        tech_hist = context_builder._historical_block(uid, tech, s)
        fin_prog = progress_svc.channel_progress(uid, fin, s)
    assert tech_hist["session_count"] == 2          # finance not mixed in
    assert fin_prog["completed_session_count"] == 1  # tech not mixed in


# ─────────────────────────────────────────────────────────────────────────────
# Backboard integration (mocked)
# ─────────────────────────────────────────────────────────────────────────────

_VALID_AI_JSON = json.dumps({
    "scores": {"clarity": 80, "conciseness": 70, "pace": 75, "volume": 82, "confidence": 68, "structure": 77},
    "overall_score": 75,
    "current_session_summary": "Strong, well-structured delivery.",
    "strongest_moments": [{"segment_index": 0, "timestamp_start": 0, "timestamp_end": 60,
                           "reason": "clear opening", "evidence": "Good morning..."}],
    "priority_moments": [{"segment_index": 0, "timestamp_start": 0, "timestamp_end": 60,
                          "dimension": "pace", "reason": "rushed", "evidence": "188 WPM",
                          "recommendation": "slow down"}],
    "improvements_since_previous": [{"dimension": "clarity", "previous": 71, "current": 80,
                                     "explanation": "clearer transitions", "evidence": "..."}],
    "regressions_since_previous": [],
    "persistent_patterns": [{"pattern": "rushes technical sections", "sessions_observed": 2,
                             "trend": "improving", "explanation": "..."}],
    "new_patterns": [],
    "stable_strengths": ["strong introductions"],
    "metrics_interpretation": {"pace": "147 WPM avg", "volume": "consistent", "pitch": "",
                               "pauses": "", "fillers": "low", "hedging": "moderate"},
    "top_3_next_session_goals": [{"goal": "Keep architecture under 165 WPM", "reason": "clarity",
                                  "measurement": "<=165 WPM"}],
    "historical_summary": {"baseline_overall_score": 61, "previous_overall_score": 70,
                           "current_overall_score": 75, "improvement_from_baseline_percent": 22.95},
})


def _enable_backboard_mock(monkeypatch, captured):
    monkeypatch.setattr(backboard, "enabled", lambda: True)

    async def _ensure(user_id):
        return "assistant-mock"

    async def _generate(user_id, assistant_id, thread_id, message, *, memory="Readonly"):
        captured.append({"message": message, "memory": memory, "assistant_id": assistant_id})
        return _VALID_AI_JSON, "backboard-thread-1"

    monkeypatch.setattr(backboard, "ensure_coach_assistant", _ensure)
    monkeypatch.setattr(backboard, "generate", _generate)


def test_backboard_receives_current_and_historical_context(monkeypatch):
    uid = _mk_user()
    cid = _channel_id()
    # One prior completed session (stub) to create history.
    _run_session(uid, cid, [_seg(0, "Prior session, clear and steady.", FULL_AUDIO)])

    captured = []
    _enable_backboard_mock(monkeypatch, captured)

    sid = _run_session(uid, cid, [_seg(0, "Current session, explaining the API gateway and database.", FULL_AUDIO)])

    assert captured, "Backboard.generate should have been called"
    msg = captured[-1]["message"]
    # Current transcript is present...
    assert "API gateway" in msg
    # ...and historical performance context is included.
    assert "historical" in msg and "previous" in msg.lower()
    # Analysis used memory="Auto" at session end.
    assert captured[-1]["memory"] == "Auto"

    with Session(engine) as s:
        fb = sessions_svc.get_feedback(sid, s)
    assert fb.clarity_score == 80.0
    assert fb.persistent_patterns  # AI structured output persisted


def test_malformed_ai_output_marks_session_failed(monkeypatch):
    uid = _mk_user()
    cid = _channel_id()
    monkeypatch.setattr(backboard, "enabled", lambda: True)

    async def _ensure(user_id):
        return "assistant-mock"

    async def _bad(user_id, assistant_id, thread_id, message, *, memory="Readonly"):
        return "this is not json", None

    monkeypatch.setattr(backboard, "ensure_coach_assistant", _ensure)
    monkeypatch.setattr(backboard, "generate", _bad)

    with Session(engine) as s:
        ts, _ = sessions_svc.create_session(uid, cid, "bad", s)
        sessions_svc.ingest_segment(ts.id, uid, _seg(0, "Some words here for analysis.", FULL_AUDIO), s)
        with pytest.raises(Exception) as exc:
            asyncio.run(sessions_svc.complete_session(ts.id, uid, s))
        assert "AI_ANALYSIS_FAILED" in str(getattr(exc.value, "code", "")) or "AI analysis" in str(exc.value)
        refreshed = sessions_svc.get_owned_session(ts.id, uid, s)
        assert refreshed.status == "FAILED"


def test_no_volume_fabrication_even_if_ai_returns_score(monkeypatch):
    uid = _mk_user()
    cid = _channel_id()
    monkeypatch.setattr(backboard, "enabled", lambda: True)

    async def _ensure(user_id):
        return "assistant-mock"

    async def _gen(user_id, assistant_id, thread_id, message, *, memory="Readonly"):
        return _VALID_AI_JSON, "tid"  # includes volume=82

    monkeypatch.setattr(backboard, "ensure_coach_assistant", _ensure)
    monkeypatch.setattr(backboard, "generate", _gen)

    # NO audio metrics supplied for this session.
    sid = _run_session(uid, cid, [_seg(0, "Talking without any audio metrics attached here.")])
    with Session(engine) as s:
        fb = sessions_svc.get_feedback(sid, s)
    assert fb.volume_score is None
    assert "volume" in (fb.unavailable_dimensions or [])
