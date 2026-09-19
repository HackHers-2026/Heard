"""Heard v2 backend tests — auth, channels, sessions, scoring, leaderboard, DMs.

External AI is stubbed (no live Backboard/Gemini calls). Auth is overridden per
test so we exercise ownership logic without a live Supabase token.
"""
import asyncio
import types
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.database import engine
from app.dependencies import get_current_user
from app.services import (
    backboard, channels as channels_svc, sessions as sessions_svc,
    profiles as profiles_svc, progress as progress_svc, analysis,
)

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _stub_ai(monkeypatch):
    """Force deterministic no-network AI (Backboard disabled) for every test."""
    monkeypatch.setattr(backboard, "enabled", lambda: False)
    yield


@pytest.fixture(autouse=True)
def _seed_channels():
    with Session(engine) as s:
        channels_svc.seed_channels(s)
    yield


def _mk_user(name="Test User") -> str:
    uid = f"user-{uuid.uuid4()}"
    with Session(engine) as s:
        profiles_svc.ensure_profile(uid, s, display_name=name, email=f"{uid}@ex.com")
    return uid


def auth_as(uid: str):
    """Return a helper that calls the client authenticated as `uid`."""
    def call(method, path, **kwargs):
        app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(id=uid, name="Test")
        try:
            return getattr(client, method)(path, **kwargs)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
    return call


def _tech_channel_id() -> str:
    with Session(engine) as s:
        return channels_svc.get_channel("technology", s).id


# ─────────────────────────────────────────────────────────────────────────────
# Auth + channels
# ─────────────────────────────────────────────────────────────────────────────

def test_auth_rejected_without_token():
    r = client.get("/api/channels")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_channel_listing():
    call = auth_as(_mk_user())
    r = call("get", "/api/channels")
    assert r.status_code == 200
    channels = r.json()["channels"]
    slugs = {c["slug"] for c in channels}
    assert {"technology", "finance", "law", "marketing",
            "healthcare", "education", "general"} <= slugs


def test_channel_seed_is_idempotent():
    with Session(engine) as s:
        created = channels_svc.seed_channels(s)
    assert created == 0  # already seeded by fixture


def test_join_and_my_channels():
    call = auth_as(_mk_user())
    cid = _tech_channel_id()
    assert call("post", f"/api/channels/{cid}/join").status_code == 200
    mine = call("get", "/api/me/channels").json()["channels"]
    assert any(c["id"] == cid for c in mine)


# ─────────────────────────────────────────────────────────────────────────────
# Sessions + segments
# ─────────────────────────────────────────────────────────────────────────────

def test_start_session_creates_post_training_thread():
    call = auth_as(_mk_user())
    cid = _tech_channel_id()
    r = call("post", f"/api/channels/{cid}/sessions", json={"title": "AWS Practice"})
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] and data["thread_id"]
    assert data["thread"]["thread_type"] == "POST_TRAINING"
    assert data["thread"]["session_id"] == data["session_id"]


def test_submit_segment_and_duplicate_rejected():
    call = auth_as(_mk_user())
    cid = _tech_channel_id()
    sid = call("post", f"/api/channels/{cid}/sessions", json={}).json()["session_id"]

    payload = {
        "segment_index": 0,
        "transcript": "Good morning everyone, today I will explain our architecture.",
        "start_seconds": 0, "end_seconds": 60,
        "audio_metrics": {"average_rms": 0.18, "rms_variance": 0.03, "silence_ratio": 0.08},
    }
    r1 = call("post", f"/api/sessions/{sid}/segments", json=payload)
    assert r1.status_code == 200
    assert r1.json()["segment"]["word_count"] > 0

    r2 = call("post", f"/api/sessions/{sid}/segments", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DUPLICATE_SEGMENT"


def test_complete_session_produces_feedback():
    call = auth_as(_mk_user())
    cid = _tech_channel_id()
    sid = call("post", f"/api/channels/{cid}/sessions", json={}).json()["session_id"]
    call("post", f"/api/sessions/{sid}/segments", json={
        "segment_index": 0,
        "transcript": "Um, so basically I think we should, like, maybe consider this approach.",
        "start_seconds": 0, "end_seconds": 60,
        "audio_metrics": {"rms_variance": 0.02, "silence_ratio": 0.1},
    })
    r = call("post", f"/api/sessions/{sid}/complete")
    assert r.status_code == 200
    fb = r.json()["feedback"]
    assert 0 <= fb["overall_score"] <= 100
    assert fb["filler_count"] >= 1
    # Second completion is a conflict.
    assert call("post", f"/api/sessions/{sid}/complete").status_code == 409


def test_cannot_access_another_users_session():
    owner = auth_as(_mk_user())
    cid = _tech_channel_id()
    sid = owner("post", f"/api/channels/{cid}/sessions", json={}).json()["session_id"]

    intruder = auth_as(_mk_user())
    r = intruder("get", f"/api/sessions/{sid}")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SESSION_FORBIDDEN"


def test_missing_audio_metrics_leaves_volume_null():
    call = auth_as(_mk_user())
    cid = _tech_channel_id()
    sid = call("post", f"/api/channels/{cid}/sessions", json={}).json()["session_id"]
    call("post", f"/api/sessions/{sid}/segments", json={
        "segment_index": 0,
        "transcript": "Here is a clear opening, a solid middle, and a strong close.",
        "start_seconds": 0, "end_seconds": 60,
    })
    fb = call("post", f"/api/sessions/{sid}/complete").json()["feedback"]
    assert fb["scores"]["volume"] is None
    assert "volume" in fb["unavailable_dimensions"]
    assert fb["overall_score"] is not None  # computed from available dims


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic scoring + improvement (unit)
# ─────────────────────────────────────────────────────────────────────────────

def test_pace_and_confidence_scoring():
    assert analysis.pace_score(140) == 100.0
    assert analysis.pace_score(300) == 20.0
    assert analysis.confidence_score(0, 0) == 100.0
    assert analysis.confidence_score(10, 5) < 100.0


def test_filler_context_handling_for_like():
    # "like the" is a real usage; standalone "like" is filler.
    assert analysis.count_fillers("I like the idea")["filler_count"] == 0
    assert analysis.count_fillers("we should, like, do this")["filler_count"] == 1


def test_composite_excludes_missing_volume():
    score = analysis.composite_score(
        {"clarity": 80, "conciseness": 75, "volume": None,
         "pace": 60, "confidence": 70, "structure": 90}
    )
    assert score == round((80 + 75 + 60 + 70 + 90) / 5, 2)


def test_improvement_calculation():
    result = progress_svc.compute_improvement([60.0, 70.0, 80.0])
    assert result["baseline_score"] == 60.0
    assert result["improvement_percent"] == pytest.approx(round((70.0 - 60.0) / 60.0 * 100, 2))
    # Fewer than 2 sessions → no improvement number yet.
    assert progress_svc.compute_improvement([60.0])["improvement_percent"] is None
    # Negative improvement is not clamped.
    assert progress_svc.compute_improvement([80.0, 40.0])["improvement_percent"] < 0


# ─────────────────────────────────────────────────────────────────────────────
# Leaderboard + recommended peers
# ─────────────────────────────────────────────────────────────────────────────

def _run_completed_session(uid: str, channel_id: str, transcript: str):
    """Create + complete a session for a user (service layer, AI stubbed)."""
    with Session(engine) as s:
        ts, _ = sessions_svc.create_session(uid, channel_id, "t", s)
        sessions_svc.ingest_segment(ts.id, uid, {
            "segment_index": 0, "transcript": transcript,
            "start_seconds": 0, "end_seconds": 60,
            "audio_metrics": {"rms_variance": 0.02, "silence_ratio": 0.05},
        }, s)
        asyncio.run(sessions_svc.complete_session(ts.id, uid, s))


def test_leaderboard_ranks_by_improvement_and_excludes_current_user():
    cid = _tech_channel_id()
    strong = _mk_user("Strong Improver")
    flat = _mk_user("Flat Speaker")

    # Two completed sessions each → eligible.
    for _ in range(2):
        _run_completed_session(strong, cid, "Clear, direct, well structured delivery today.")
        _run_completed_session(flat, cid, "Um like uh basically you know sort of maybe.")

    call = auth_as(strong)
    lb = call("get", f"/api/channels/{cid}/leaderboard").json()
    assert lb["total"] >= 2
    assert lb["viewer_rank"] is not None
    ranks = [e["improvement_percent"] for e in lb["entries"]]
    assert ranks == sorted(ranks, reverse=True)

    peers = call("get", f"/api/channels/{cid}/recommended-peers").json()["peers"]
    assert all(p["user_id"] != strong for p in peers)
    assert len(peers) <= 3


# ─────────────────────────────────────────────────────────────────────────────
# Direct messages
# ─────────────────────────────────────────────────────────────────────────────

def test_dm_create_send_and_authorization():
    a = _mk_user("Alice")
    b = _mk_user("Bob")
    intruder = _mk_user("Eve")

    call_a = auth_as(a)
    convo = call_a("post", f"/api/dms/with/{b}").json()
    cid = convo["conversation_id"]

    # Idempotent: same pair returns same conversation.
    assert call_a("post", f"/api/dms/with/{b}").json()["conversation_id"] == cid

    assert call_a("post", f"/api/dms/{cid}/messages", json={"content": "Hi Bob"}).status_code == 200

    # Intruder cannot read the conversation.
    r = auth_as(intruder)("get", f"/api/dms/{cid}/messages")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "DM_FORBIDDEN"

    # Bob sees an unread message.
    convos = auth_as(b)("get", "/api/dms").json()["conversations"]
    mine = next(c for c in convos if c["id"] == cid)
    assert mine["unread_count"] == 1


def test_cannot_dm_self():
    a = _mk_user("Solo")
    r = auth_as(a)("post", f"/api/dms/with/{a}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "DM_SELF"
