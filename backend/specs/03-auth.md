# Spec 03 — Auth

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file.  
**Requires:** Spec 01 + 02 done.

## Flow
1. Frontend calls Supabase magic link → user gets email → clicks link → Supabase issues JWT
2. Frontend sends `Authorization: Bearer <jwt>` on every request
3. Backend validates JWT in `get_current_user`, upserts user on first login

## dependencies.py
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
from sqlmodel import Session, select
from app.models import User

bearer = HTTPBearer()

def get_current_user(token = Depends(bearer), session = Depends(get_session)) -> User:
    try:
        payload = jwt.decode(
            token.credentials,
            os.getenv("SUPABASE_JWT_SECRET"),
            algorithms=["HS256"],
            audience="authenticated"
        )
        email = payload.get("email")
        sub = payload.get("sub")           # Supabase user UUID
    except JWTError:
        raise HTTPException(status_code=401)

    user = session.exec(select(User).where(User.linkedin_id == sub)).first()
    if not user:
        user = User(linkedin_id=sub, name=email, id=sub)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
```

## Env var needed
```
SUPABASE_JWT_SECRET=   # found in Supabase project settings → API → JWT secret
```

## Tests (`tests/test_auth.py`)

```python
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
client = TestClient(app)

def test_no_token_returns_401():
    r = client.get("/api/profile/some-id")
    assert r.status_code == 401

def test_invalid_token_returns_401():
    r = client.get("/api/profile/some-id", headers={"Authorization": "Bearer bad.token.here"})
    assert r.status_code == 401

def test_valid_token_creates_user_on_first_login():
    # Mock jwt.decode to return a valid payload
    payload = {"sub": "supabase-uid-123", "email": "test@example.com"}
    with patch("app.dependencies.jwt.decode", return_value=payload):
        r = client.post("/api/speech/start", headers={"Authorization": "Bearer fake"})
        assert r.status_code == 200
        data = r.json()
        assert "speech_id" in data
        assert "session_token" in data
```

## Done when
All tests pass: `pytest tests/test_auth.py`
