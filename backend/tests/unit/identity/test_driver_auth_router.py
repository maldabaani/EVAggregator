from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.gateway.refresh_store import InMemoryRefreshTokenStore
from evagg.identity.driver_auth import InMemoryDriverAccountStore
from evagg.identity.driver_auth_router import build_driver_auth_router


def _build_app():
    store = InMemoryDriverAccountStore()
    refresh_store = InMemoryRefreshTokenStore()

    async def get_store():
        return store

    async def get_refresh_store():
        return refresh_store

    app = FastAPI()
    app.include_router(build_driver_auth_router(get_store, get_refresh_store))
    return app, store, refresh_store


def test_signup_returns_a_session_without_leaking_the_password():
    app, _, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["driver"]["email"] == "driver@example.com"
    assert "password" not in body["driver"]
    assert "password_hash" not in body["driver"]
    assert len(body["access_token"]) > 0
    assert len(body["refresh_token"]) > 0


def test_signup_rejects_a_malformed_email():
    app, _, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "not-an-email", "full_name": "Jane Driver", "password": "hunter2"},
    )

    assert response.status_code == 422


def test_signup_twice_with_the_same_email_returns_409():
    app, _, _ = _build_app()
    client = TestClient(app)
    client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    )

    response = client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Someone Else", "password": "different"},
    )

    assert response.status_code == 409


def test_login_with_correct_credentials_succeeds():
    app, _, _ = _build_app()
    client = TestClient(app)
    client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    )

    response = client.post("/auth/login", json={"email": "driver@example.com", "password": "hunter2"})

    assert response.status_code == 200
    assert response.json()["driver"]["email"] == "driver@example.com"


def test_login_with_wrong_password_returns_401():
    app, _, _ = _build_app()
    client = TestClient(app)
    client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    )

    response = client.post("/auth/login", json={"email": "driver@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_login_with_unknown_email_returns_401():
    app, _, _ = _build_app()
    client = TestClient(app)

    response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})

    assert response.status_code == 401


def test_refresh_rotates_the_token_and_returns_a_new_access_token():
    app, _, _ = _build_app()
    client = TestClient(app)
    login = client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    ).json()

    response = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] != login["refresh_token"]
    assert body["driver"]["email"] == "driver@example.com"


def test_refresh_with_an_already_rotated_token_is_rejected():
    app, _, _ = _build_app()
    client = TestClient(app)
    login = client.post(
        "/auth/signup",
        json={"email": "driver@example.com", "full_name": "Jane Driver", "password": "hunter2"},
    ).json()
    client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})

    response = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 401


def test_refresh_with_an_unknown_token_returns_401():
    app, _, _ = _build_app()
    client = TestClient(app)

    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401
