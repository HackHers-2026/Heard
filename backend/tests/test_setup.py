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
