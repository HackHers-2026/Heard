# Spec 07 — Component Test (Full Backend)

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file.  
**Requires:** All specs 01–06 done and their unit tests passing.  
**No MCPs needed** — tests run against in-memory SQLite.

This test walks the complete happy path end-to-end through the real API,
with all services in stub mode (no external API keys needed).

---

## Tests (`tests/test_component.py`)

```python
import pytest, os
os.environ.pop("GEMINI_API_KEY", None)   # stub mode

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)
MOCK_USER = MagicMock(id="user-comp-1", name="Component Test User", is_mentor=False)

def authed(method, path, **kwargs):
    with patch("app.dependencies.get_current_user", return_value=MOCK_USER):
        return getattr(client, method)(path, headers={"Authorization": "Bearer fake"}, **kwargs)


# ── Flow 1: Pre-speech encouragement ─────────────────────────────────────────

def test_flow_encourage_quick():
    r = authed("post", "/api/encourage", json={"mode": "quick"})
    assert r.status_code == 200
    assert isinstance(r.json()["message"], str)

def test_flow_encourage_plan():
    r = authed("post", "/api/encourage", json={"mode": "plan", "context": "board meeting"})
    assert r.status_code == 200
    data = r.json()
    assert "message" in data
    assert "outline" in data and len(data["outline"]) > 0


# ── Flow 2 + 3: Live speech → post-speech report ─────────────────────────────

@pytest.fixture
def full_speech():
    """Runs a complete speech session and returns the speech_id."""
    start = authed("post", "/api/speech/start").json()
    speech_id = start["speech_id"]
    token = start["session_token"]

    # 3 segments
    for i in range(3):
        r = client.post("/api/speech/segment", headers={"Authorization": f"Bearer {token}"}, json={
            "speech_id": speech_id,
            "transcript": f"Segment {i} hello world um so basically I think",
            "segment_index": i,
            "recorded_at": f"2026-01-01T00:0{i}:00",
            "duration_seconds": 120.0,
            "avg_volume": 65,
            "volume_variance": 8,
        })
        assert r.status_code == 200
        assert "nudge" in r.json()

    end = client.post("/api/speech/end", headers={"Authorization": f"Bearer {token}"},
                      json={"speech_id": speech_id})
    assert end.status_code == 200
    return speech_id

def test_flow_speech_report_available(full_speech):
    r = authed("get", f"/api/speech/{full_speech}/report")
    assert r.status_code == 200
    data = r.json()
    assert data["speech"]["status"] == "done"
    metrics = data["metrics"]
    for dim in ["clarity", "volume", "pace", "confidence", "structure", "overall"]:
        assert 0 <= metrics[dim] <= 100
    assert isinstance(metrics["summary"], str)
    assert isinstance(metrics["suggestions"], list)


# ── Flow 4: Community feed ────────────────────────────────────────────────────

def test_flow_feed_and_like(full_speech):
    # Post to community
    post_r = authed("post", "/api/feed", json={"speech_id": full_speech, "career_tag": "engineering"})
    assert post_r.status_code == 200
    post_id = post_r.json()["id"]

    # Feed returns the post
    feed = authed("get", "/api/feed").json()
    assert any(p["id"] == post_id for p in feed["posts"])

    # Like it
    like_r = authed("post", f"/api/feed/{post_id}/like")
    assert like_r.status_code == 200
    assert like_r.json()["liked"] == True
    assert like_r.json()["like_count"] == 1

    # Unlike
    unlike_r = authed("post", f"/api/feed/{post_id}/like")
    assert unlike_r.json()["liked"] == False
    assert unlike_r.json()["like_count"] == 0


# ── Flow 5: Profile ───────────────────────────────────────────────────────────

def test_flow_profile_radar_data(full_speech):
    r = authed("get", f"/api/profile/{MOCK_USER.id}")
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    assert "average_metrics" in data
    avg = data["average_metrics"]
    for dim in ["clarity", "volume", "pace", "confidence", "structure", "overall"]:
        assert dim in avg


# ── Mentor connection ─────────────────────────────────────────────────────────

def test_flow_mentor_connect(full_speech):
    r = authed("post", "/api/mentor/connect", json={
        "mentor_id": "some-mentor-id",
        "speech_id": full_speech
    })
    assert r.status_code == 200
    conn = r.json()["connection"]
    assert conn["status"] == "pending"
    assert conn["mentor_id"] == "some-mentor-id"
```

---

## Done when

All tests pass: `pytest tests/test_component.py`

Every flow in the product is covered by at least one assertion end-to-end.
