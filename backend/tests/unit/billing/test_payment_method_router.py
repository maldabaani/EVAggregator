import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.billing.payment_method_router import build_payment_method_router
from evagg.billing.payment_methods import InMemoryPaymentMethodStore

WALLET_ID = uuid.uuid4()


def _build_app():
    store = InMemoryPaymentMethodStore()

    async def get_store():
        return store

    app = FastAPI()
    app.include_router(build_payment_method_router(get_store))
    return app, store


def test_get_payment_method_with_none_set_returns_null_data():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get(f"/wallet/{WALLET_ID}/payment-method")

    assert response.status_code == 200
    assert response.json() == {"data": None}


def test_setting_a_wallet_balance_method_needs_no_psp_token():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(f"/wallet/{WALLET_ID}/payment-method", json={"type": "wallet_balance"})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "wallet_balance"
    assert body["is_default"] is True


def test_setting_a_direct_card_method_requires_a_psp_token():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(f"/wallet/{WALLET_ID}/payment-method", json={"type": "direct_card"})

    assert response.status_code == 422


def test_setting_a_direct_card_method_with_a_token_succeeds():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        f"/wallet/{WALLET_ID}/payment-method", json={"type": "direct_card", "psp_token": "tok-1"}
    )

    assert response.status_code == 200
    assert response.json()["psp_token"] == "tok-1"


def test_an_invalid_type_is_rejected():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(f"/wallet/{WALLET_ID}/payment-method", json={"type": "bogus"})

    assert response.status_code == 422


def test_setting_replaces_the_previous_default():
    app, store = _build_app()
    client = TestClient(app)
    client.post(f"/wallet/{WALLET_ID}/payment-method", json={"type": "wallet_balance"})

    client.post(f"/wallet/{WALLET_ID}/payment-method", json={"type": "direct_card", "psp_token": "tok-1"})

    response = client.get(f"/wallet/{WALLET_ID}/payment-method")
    assert response.json()["data"]["type"] == "direct_card"
