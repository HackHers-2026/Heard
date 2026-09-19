from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app
from app.dependencies import get_current_user

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
