"""The Tauri webview is cross-origin (https://tauri.localhost): any method
outside the CORS allow-list is blocked by the browser before it reaches the
service. DELETE /conversations must survive the preflight (v0.1.4 bug)."""
from fastapi.testclient import TestClient

from app.main import app


def test_delete_preflight_allowed():
    client = TestClient(app)
    r = client.options("/api/conversations/abc123", headers={
        "Origin": "https://tauri.localhost",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code == 200
    assert "DELETE" in r.headers["access-control-allow-methods"]


def test_post_and_get_preflight_still_allowed():
    client = TestClient(app)
    for method in ("GET", "POST"):
        r = client.options("/api/conversations", headers={
            "Origin": "https://tauri.localhost",
            "Access-Control-Request-Method": method,
        })
        assert r.status_code == 200
