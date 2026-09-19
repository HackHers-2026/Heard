from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from uuid import uuid4

from sqlmodel import Session

from app.main import app
from app.dependencies import get_current_user
from app.database import engine
from app.models import ChatMessage, MentorConnection, Speech, User

client = TestClient(app)

AUTH = {"Authorization": "Bearer fake"}
MOCK_USER = MagicMock(id="user-routes-1", name="Test")


def authed(method, path, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    try:
        return getattr(client, method)(path, headers=AUTH, **kwargs)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_encourage_quick():
    r = authed("post", "/api/encourage", json={"mode": "quick"})
    assert r.status_code == 200
    assert "message" in r.json()


def test_encourage_plan_returns_outline():
    r = authed("post", "/api/encourage", json={"mode": "plan", "context": "pitch to investors"})
    assert r.status_code == 200
    assert "outline" in r.json()


def test_speech_start():
    r = authed("post", "/api/speech/start")
    assert r.status_code == 200
    assert "speech_id" in r.json()
    assert "session_token" in r.json()


def test_speech_segment_returns_nudge():
    start = authed("post", "/api/speech/start").json()
    r = client.post("/api/speech/segment", headers=AUTH, json={
        "speech_id": start["speech_id"],
        "transcript": "hello world",
        "segment_index": 0,
        "recorded_at": "2026-01-01T00:00:00",
        "duration_seconds": 120,
        "avg_volume": 60,
        "volume_variance": 5,
    })
    assert r.status_code == 200
    assert "nudge" in r.json()


def test_feed_returns_list():
    r = authed("get", "/api/feed")
    assert r.status_code == 200
    assert "posts" in r.json()
    assert "next_cursor" in r.json()


def test_unauthenticated_routes_return_401():
    for method, path in [("get", "/api/feed"), ("post", "/api/speech/start")]:
        r = getattr(client, method)(path)
        assert r.status_code == 401


def test_dashboard_bootstrap_returns_user_speeches_and_contacts():
    user_id = f"user-{uuid4()}"
    mentor_id = f"mentor-{uuid4()}"
    speech_id = f"speech-{uuid4()}"

    dashboard_user = MagicMock(id=user_id, name="Dashboard User")
    app.dependency_overrides[get_current_user] = lambda: dashboard_user
    try:
        with Session(engine) as session:
            session.add(User(id=user_id, name="Dashboard User", linkedin_id=user_id))
            session.add(User(id=mentor_id, name="Mentor One", linkedin_id=mentor_id, is_mentor=True))
            session.add(Speech(id=speech_id, user_id=user_id))
            session.add(
                ChatMessage(
                    speech_id=speech_id,
                    session_hash=f"hash-{uuid4()}",
                    role="model",
                    phase="preptalk",
                    content="Great opening line.",
                    summary="Opening line",
                )
            )
            session.add(
                MentorConnection(
                    requester_id=user_id,
                    mentor_id=mentor_id,
                    speech_id=speech_id,
                )
            )
            session.commit()

        r = client.get("/api/dashboard/bootstrap", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["id"] == user_id
        assert data["speeches"][0]["id"] == speech_id
        assert data["speeches"][0]["last_message"] == "Great opening line."
        assert data["contacts"][0]["id"] == mentor_id
        assert data["contacts"][0]["speech_id"] == speech_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)
