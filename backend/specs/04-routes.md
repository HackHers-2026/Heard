# Spec 04 — API Routes

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file.  
**Requires:** Specs 01–03 done. Services can be stubs — routes first, wire services after.

All routes are in `app/routers/`. Register all in `main.py` with prefix `/api`.

---

## encourage.py
```
POST /api/encourage
Body: { mode: "quick" | "plan", context?: str }
Auth: required
→ calls services/gemini.py:encourage()
→ returns { message: str, outline?: list[str] }
```

## speech.py
```
POST /api/speech/start
Auth: required
→ create Speech(user_id, status="live")
→ generate session_token (sign with secret or use speech.id)
→ return { speech_id, session_token }

POST /api/speech/segment
Auth: session_token (bearer)
Body: { speech_id, transcript, segment_index, recorded_at, duration_seconds, avg_volume, volume_variance }
→ save RealtimeSegment
→ calls services/gemini.py:nudge() — drop if > 3s, return null nudge
→ return { nudge: str | null }

POST /api/speech/end
Auth: session_token (bearer)
Body: { speech_id }
→ set Speech.status = "done", ended_at = now
→ trigger services/gemini.py:score() async (background task)
→ return { report_ready: false }

GET /api/speech/{speech_id}/report
Auth: required
→ fetch Speech + SpeechMetrics
→ return { speech, metrics } or 404 if not done yet
```

## feed.py
```
GET /api/feed
Auth: required
Query: career_tag?, topic_tag?, cursor?, limit=20
→ paginated CommunityPost + joined User + SpeechMetrics
→ return { posts: [...], next_cursor: str | null }

POST /api/feed/{post_id}/like
Auth: required
→ toggle Like row
→ update CommunityPost.like_count
→ return { liked: bool, like_count: int }
```

## profile.py
```
GET /api/profile/{user_id}
Auth: required
→ fetch User
→ calls services/scoring.py:top_speeches(user_id)
→ calls services/scoring.py:average_metrics(speeches)
→ return { user, top_speeches, average_metrics }
```

## mentor.py
```
POST /api/mentor/connect
Auth: required
Body: { mentor_id, speech_id }
→ create MentorConnection(status="pending")
→ return { connection }
```

## Tests (`tests/test_routes.py`)

```python
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
client = TestClient(app)

AUTH = {"Authorization": "Bearer fake"}
MOCK_USER = MagicMock(id="user-1", name="Test")

def authed(method, path, **kwargs):
    with patch("app.dependencies.get_current_user", return_value=MOCK_USER):
        return getattr(client, method)(path, headers=AUTH, **kwargs)

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
        "speech_id": start["speech_id"], "transcript": "hello world",
        "segment_index": 0, "recorded_at": "2026-01-01T00:00:00",
        "duration_seconds": 120, "avg_volume": 60, "volume_variance": 5
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
```

## Done when
All tests pass: `pytest tests/test_routes.py`
