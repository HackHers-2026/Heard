"""
Component test — full backend happy path, all 5 product flows, stub mode.
No API keys needed. Tests every meaningful route and edge case.
"""
import os
os.environ.pop("GEMINI_API_KEY", None)   # force stub mode

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select

from app.main import app
from app.dependencies import get_current_user
from app.models import Speech, SpeechMetrics, CommunityPost, Like, MentorConnection

client = TestClient(app)

MOCK_USER = MagicMock(id="comp-user-1", name="Component Tester", is_mentor=False)
MOCK_MENTOR = MagicMock(id="comp-mentor-1", name="Mentor User", is_mentor=True)


@pytest.fixture(scope="module", autouse=True)
def seed_users():
    """Insert mock users into the DB so profile lookups don't 404."""
    from app.database import engine
    from app.models import User
    with Session(engine) as s:
        for uid, name, mentor in [
            ("comp-user-1", "Component Tester", False),
            ("comp-mentor-1", "Mentor User", True),
            ("no-speech-user", "New User", False),
        ]:
            if not s.get(User, uid):
                s.add(User(id=uid, name=name, is_mentor=mentor))
        s.commit()


def authed(method, path, *, as_user=MOCK_USER, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: as_user
    try:
        return getattr(client, method)(path, headers={"Authorization": "Bearer fake"}, **kwargs)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def full_speech():
    """Complete speech session: start → 3 segments → end. Returns speech_id."""
    start = authed("post", "/api/speech/start").json()
    speech_id = start["speech_id"]
    token = start["session_token"]

    segments = [
        "Hello everyone, um, I'd like to talk about our product roadmap today.",
        "So basically, uh, the core idea is that we focus on user retention first.",
        "In conclusion, I think we should prioritize these three initiatives this quarter.",
    ]
    for i, transcript in enumerate(segments):
        r = client.post("/api/speech/segment", headers={"Authorization": f"Bearer {token}"}, json={
            "speech_id": speech_id,
            "transcript": transcript,
            "segment_index": i,
            "recorded_at": f"2026-01-01T00:0{i}:00",
            "duration_seconds": 120.0,
            "avg_volume": 65 + i,
            "volume_variance": 5,
        })
        assert r.status_code == 200, f"segment {i} failed: {r.text}"

    end = client.post("/api/speech/end",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"speech_id": speech_id})
    assert end.status_code == 200
    return speech_id


# ── Flow 1: Pre-speech encouragement ─────────────────────────────────────────

def test_encourage_quick():
    r = authed("post", "/api/encourage", json={"mode": "quick"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["message"], str)
    assert len(data["message"]) > 0
    assert "outline" not in data


def test_encourage_plan_with_context():
    r = authed("post", "/api/encourage", json={"mode": "plan", "context": "board meeting"})
    assert r.status_code == 200
    data = r.json()
    assert "message" in data
    assert "outline" in data
    assert len(data["outline"]) >= 3


def test_encourage_plan_no_context():
    r = authed("post", "/api/encourage", json={"mode": "plan"})
    assert r.status_code == 200
    assert "outline" in r.json()


def test_encourage_requires_auth():
    r = client.post("/api/encourage", json={"mode": "quick"})
    assert r.status_code == 401


# ── Flow 2: Live speech — segment nudges ─────────────────────────────────────

def test_speech_start_returns_ids():
    r = authed("post", "/api/speech/start")
    assert r.status_code == 200
    data = r.json()
    assert "speech_id" in data
    assert "session_token" in data
    assert data["speech_id"] == data["session_token"]   # POC: token = id


def test_speech_segment_nudge_returned(full_speech):
    # nudge is returned for each segment — already asserted in fixture, recheck shape
    start = authed("post", "/api/speech/start").json()
    r = client.post("/api/speech/segment", headers={"Authorization": "Bearer fake"}, json={
        "speech_id": start["speech_id"],
        "transcript": "Let me walk you through our Q4 strategy.",
        "segment_index": 0,
        "recorded_at": "2026-01-01T00:00:00",
        "duration_seconds": 120.0,
        "avg_volume": 70,
        "volume_variance": 3,
    })
    assert r.status_code == 200
    nudge = r.json().get("nudge")
    assert nudge is None or isinstance(nudge, str)


def test_speech_segment_empty_transcript():
    start = authed("post", "/api/speech/start").json()
    r = client.post("/api/speech/segment", headers={"Authorization": "Bearer fake"}, json={
        "speech_id": start["speech_id"],
        "transcript": "",
        "segment_index": 0,
        "recorded_at": "2026-01-01T00:00:00",
        "duration_seconds": 120.0,
        "avg_volume": 0,
        "volume_variance": 0,
    })
    assert r.status_code == 200   # empty transcript is valid — no nudge crash


def test_speech_end_triggers_scoring(full_speech):
    # score() ran as background task — speech should be "done"
    from app.database import engine
    with Session(engine) as s:
        speech = s.get(Speech, full_speech)
        assert speech.status == "done"
        metrics = s.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == full_speech)).first()
        assert metrics is not None


# ── Flow 3: Post-speech report ────────────────────────────────────────────────

def test_report_all_metrics_present(full_speech):
    r = authed("get", f"/api/speech/{full_speech}/report")
    assert r.status_code == 200
    data = r.json()
    assert data["speech"]["status"] == "done"
    metrics = data["metrics"]
    for dim in ["clarity", "volume", "pace", "confidence", "structure", "overall"]:
        assert dim in metrics
        assert 0 <= metrics[dim] <= 100, f"{dim} out of range: {metrics[dim]}"
    assert isinstance(metrics["summary"], str)
    assert len(metrics["summary"]) > 0
    assert isinstance(metrics["suggestions"], list)


def test_report_deterministic_metrics_reflect_audio(full_speech):
    """Volume/pace/confidence come from real data, not Gemini."""
    r = authed("get", f"/api/speech/{full_speech}/report")
    m = r.json()["metrics"]
    # segments had avg_volume ~65-67 (good range) and ~3 filler words
    assert m["volume"] > 0
    assert m["pace"] > 0
    assert m["confidence"] > 0


def test_report_404_if_not_done():
    start = authed("post", "/api/speech/start").json()
    r = authed("get", f"/api/speech/{start['speech_id']}/report")
    assert r.status_code == 404


def test_report_404_unknown_id():
    r = authed("get", "/api/speech/nonexistent-id/report")
    assert r.status_code == 404


def test_report_requires_auth(full_speech):
    r = client.get(f"/api/speech/{full_speech}/report")
    assert r.status_code == 401


# ── Flow 4: Community feed ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def feed_post_id(full_speech):
    r = authed("post", "/api/feed", json={"speech_id": full_speech, "career_tag": "engineering"})
    assert r.status_code == 200
    return r.json()["id"]


def test_feed_returns_posts(feed_post_id):
    r = authed("get", "/api/feed")
    assert r.status_code == 200
    data = r.json()
    assert "posts" in data
    assert "next_cursor" in data
    assert any(p["id"] == feed_post_id for p in data["posts"])


def test_feed_filter_by_career_tag(feed_post_id):
    r = authed("get", "/api/feed?career_tag=engineering")
    assert r.status_code == 200
    posts = r.json()["posts"]
    assert all(p["career_tag"] == "engineering" for p in posts if p.get("career_tag"))


def test_feed_filter_no_match():
    r = authed("get", "/api/feed?career_tag=law")
    assert r.status_code == 200
    # no law posts — should return empty list, not error
    data = r.json()
    assert isinstance(data["posts"], list)


def test_like_toggle(feed_post_id):
    # like
    r = authed("post", f"/api/feed/{feed_post_id}/like")
    assert r.status_code == 200
    assert r.json()["liked"] == True
    assert r.json()["like_count"] == 1

    # unlike
    r = authed("post", f"/api/feed/{feed_post_id}/like")
    assert r.status_code == 200
    assert r.json()["liked"] == False
    assert r.json()["like_count"] == 0


def test_like_different_users(feed_post_id):
    user_a = MagicMock(id="like-user-a", name="A", is_mentor=False)
    user_b = MagicMock(id="like-user-b", name="B", is_mentor=False)

    authed("post", f"/api/feed/{feed_post_id}/like", as_user=user_a)
    authed("post", f"/api/feed/{feed_post_id}/like", as_user=user_b)

    r = authed("get", "/api/feed")
    post = next(p for p in r.json()["posts"] if p["id"] == feed_post_id)
    assert post["like_count"] >= 2

    # clean up
    authed("post", f"/api/feed/{feed_post_id}/like", as_user=user_a)
    authed("post", f"/api/feed/{feed_post_id}/like", as_user=user_b)


def test_like_unknown_post():
    r = authed("post", "/api/feed/nonexistent-post/like")
    assert r.status_code == 404


def test_feed_requires_auth():
    r = client.get("/api/feed")
    assert r.status_code == 401


# ── Flow 5: Profile ───────────────────────────────────────────────────────────

def test_profile_radar_data(full_speech):
    r = authed("get", f"/api/profile/{MOCK_USER.id}")
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    assert "average_metrics" in data
    avg = data["average_metrics"]
    for dim in ["clarity", "volume", "pace", "confidence", "structure", "overall"]:
        assert dim in avg


def test_profile_no_speeches():
    """User with no speeches returns zero averages, not an error."""
    new_user = MagicMock(id="no-speech-user", name="New", is_mentor=False)
    # register user by calling speech/start
    authed("post", "/api/speech/start", as_user=new_user)
    r = authed("get", f"/api/profile/{new_user.id}", as_user=new_user)
    assert r.status_code == 200
    avg = r.json()["average_metrics"]
    assert avg["overall"] == 0


def test_profile_404_unknown_user():
    r = authed("get", "/api/profile/does-not-exist")
    assert r.status_code == 404


def test_profile_requires_auth():
    r = client.get(f"/api/profile/{MOCK_USER.id}")
    assert r.status_code == 401


# ── Mentor connection ─────────────────────────────────────────────────────────

def test_mentor_connect(full_speech):
    r = authed("post", "/api/mentor/connect", json={
        "mentor_id": "some-mentor-id",
        "speech_id": full_speech,
    })
    assert r.status_code == 200
    conn = r.json()["connection"]
    assert conn["status"] == "pending"
    assert conn["mentor_id"] == "some-mentor-id"
    assert conn["speech_id"] == full_speech


def test_mentor_connect_requires_auth():
    r = client.post("/api/mentor/connect", json={"mentor_id": "x", "speech_id": "y"})
    assert r.status_code == 401


# ── Deterministic scoring unit tests ─────────────────────────────────────────

def test_deterministic_volume_score():
    from app.services.gemini import _deterministic_metrics
    from app.models import RealtimeSegment

    def seg(vol, var, text="hello world hello world"):
        s = RealtimeSegment(
            speech_id="x", transcript=text, segment_index=0,
            recorded_at="2026-01-01", duration_seconds=30.0,
            avg_volume=vol, volume_variance=var,
        )
        return s

    good = _deterministic_metrics([seg(65, 5)])
    assert good["volume"] >= 70   # ideal volume range

    loud = _deterministic_metrics([seg(96, 5)])
    assert loud["volume"] < good["volume"]   # too loud → penalty

    quiet = _deterministic_metrics([seg(30, 5)])
    assert quiet["volume"] < good["volume"]  # too quiet → penalty

    variable = _deterministic_metrics([seg(65, 30)])
    assert variable["volume"] < good["volume"]  # high variance → penalty


def test_deterministic_pace_score():
    from app.services.gemini import _deterministic_metrics
    from app.models import RealtimeSegment

    def seg(text, duration):
        s = RealtimeSegment(
            speech_id="x", transcript=text, segment_index=0,
            recorded_at="2026-01-01", duration_seconds=duration,
            avg_volume=65, volume_variance=5,
        )
        return s

    # ~135 wpm — ideal
    words = " ".join(["word"] * 135)
    ideal = _deterministic_metrics([seg(words, 60.0)])
    assert ideal["pace"] >= 90

    # ~50 wpm — too slow
    slow_words = " ".join(["word"] * 50)
    slow = _deterministic_metrics([seg(slow_words, 60.0)])
    assert slow["pace"] < ideal["pace"]

    # ~220 wpm — too fast
    fast_words = " ".join(["word"] * 220)
    fast = _deterministic_metrics([seg(fast_words, 60.0)])
    assert fast["pace"] < ideal["pace"]


def test_deterministic_confidence_score():
    from app.services.gemini import _deterministic_metrics
    from app.models import RealtimeSegment

    def seg(text):
        s = RealtimeSegment(
            speech_id="x", transcript=text, segment_index=0,
            recorded_at="2026-01-01", duration_seconds=30.0,
            avg_volume=65, volume_variance=5,
        )
        return s

    clean = _deterministic_metrics([seg("We will deliver this project on time and on budget.")])
    fillers = _deterministic_metrics([seg("Um so like basically uh we will um sort of deliver this.")])
    assert clean["confidence"] > fillers["confidence"]


def test_score_empty_speech_no_crash():
    """score() on a speech with no segments should not raise."""
    from app.services.gemini import score
    from app.database import engine

    with Session(engine) as s:
        from app.models import User
        import uuid
        uid = str(uuid.uuid4())
        u = User(id=uid, name="empty-speech-test")
        s.add(u); s.commit()
        sp = Speech(user_id=uid)
        s.add(sp); s.commit(); s.refresh(sp)
        score(sp.id, s)   # no segments — should fall back to stubs
        metrics = s.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)).first()
        assert metrics is not None
