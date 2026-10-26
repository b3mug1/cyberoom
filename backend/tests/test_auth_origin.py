from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.routes import _require_trusted_cookie_origin
from app.main import app


def _request(origin: str | None) -> Request:
    headers = [(b"host", b"localhost:8000")]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "scheme": "http", "server": ("localhost", 8000), "path": "/api/v1/auth/refresh", "headers": headers})


def test_same_origin_refresh_cookie_request_is_allowed() -> None:
    _require_trusted_cookie_origin(_request("http://localhost:8000"))


def test_cross_site_refresh_cookie_request_is_rejected() -> None:
    with TestClient(app) as client:
        client.cookies.set("cyberoom_refresh", "invalid")
        response = client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "https://attacker.example"},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "UNTRUSTED_ORIGIN"
