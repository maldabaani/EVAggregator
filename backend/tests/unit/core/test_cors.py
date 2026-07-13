"""Verifies the CORS configuration `main.py`/`edge_app.py` both wire up
(same `CORSMiddleware` settings, reproduced on a minimal app here rather
than importing those modules directly — they build real Redis/NATS
clients at import time, which this unit test suite doesn't have)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

from evagg.core.config import Settings


def _build_app(allowed_origins: list[str]) -> FastAPI:
    app = FastAPI()

    @app.post("/auth/signup")
    async def signup() -> dict:
        return {"ok": True}

    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins, allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )
    return app


def test_wildcard_origins_list_is_just_a_wildcard():
    settings = Settings(cors_allowed_origins="*")

    assert settings.cors_allowed_origins_list == ["*"]


def test_a_comma_separated_setting_splits_into_a_trimmed_list():
    settings = Settings(cors_allowed_origins="http://localhost:3000, http://localhost:4200")

    assert settings.cors_allowed_origins_list == ["http://localhost:3000", "http://localhost:4200"]


def test_a_preflight_request_from_an_allowed_origin_is_accepted():
    client = TestClient(_build_app(["*"]))

    response = client.options(
        "/auth/signup",
        headers={
            "Origin": "http://localhost:61062",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_a_real_post_response_carries_the_cors_header():
    client = TestClient(_build_app(["*"]))

    response = client.post("/auth/signup", headers={"Origin": "http://localhost:61062"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_a_pinned_origin_list_rejects_other_origins():
    client = TestClient(_build_app(["http://localhost:4200"]))

    response = client.options(
        "/auth/signup",
        headers={
            "Origin": "http://localhost:61062",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
