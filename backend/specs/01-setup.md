# Spec 01 — Project Setup

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file is enough to start.

## Dependencies
```
fastapi
uvicorn[standard]
sqlmodel
python-dotenv
httpx
python-jose[cryptography]   # JWT validation for Supabase auth
```

`pip install -r requirements.txt`

## Folder structure to scaffold
```
backend/
  app/
    main.py
    models.py
    schemas.py
    dependencies.py
    routers/
      __init__.py
      encourage.py
      speech.py
      feed.py
      profile.py
      mentor.py
    services/
      __init__.py
      gemini.py
      elevenlabs.py
      scoring.py
      backboard.py
      tigertable.py
  .env.example
  requirements.txt
```

## main.py
- Create FastAPI app
- Register all routers with `/api` prefix
- `GET /health` → `{ status: "ok" }`
- CORS: allow all origins for POC

## dependencies.py
- `get_session` — SQLModel session from env `DATABASE_URL`
- `get_current_user` — decode Supabase JWT from `Authorization: Bearer` header → return User or 401

## Tests (`tests/test_setup.py`)

```python
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_all_routes_registered():
    routes = [r.path for r in app.routes]
    assert "/api/encourage" in routes
    assert "/api/speech/start" in routes
    assert "/api/feed" in routes
    assert "/api/profile/{user_id}" in routes
```

## Done when
All tests pass: `pytest tests/test_setup.py`
