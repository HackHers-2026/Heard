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
    # Mock the Supabase Auth server response (GET /auth/v1/user).
    supabase_user = {"id": "supabase-uid-auth-test", "email": "test@example.com"}
    with patch("app.dependencies._fetch_supabase_user", return_value=supabase_user):
        r = client.post("/api/speech/start", headers={"Authorization": "Bearer fake"})
        assert r.status_code == 200
        data = r.json()
        assert "speech_id" in data
        assert "session_token" in data
