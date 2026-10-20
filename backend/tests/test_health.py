from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """Endpoint /health membalas status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_preflight_unggahan_octet_stream() -> None:
    """Preflight lintas origin untuk unggahan Bearer/octet-stream harus lolos."""
    resp = client.options(
        "/unggahan",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-sha256",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in resp.headers["access-control-allow-methods"]
    assert "x-sha256" in resp.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in resp.headers
