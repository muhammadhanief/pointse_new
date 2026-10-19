from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """Endpoint /health membalas status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
