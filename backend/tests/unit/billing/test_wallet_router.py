import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.billing.payment_provider import StubPaymentProvider
from evagg.billing.wallet import InMemoryWalletLedgerStore, WalletService
from evagg.billing.wallet_router import build_wallet_router

WALLET_ID = uuid.uuid4()


def _build_app():
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    service = WalletService(ledger, provider)

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_wallet_router(get_service))
    return app


def test_topup_then_webhook_updates_balance():
    client = TestClient(_build_app())

    topup_response = client.post(
        "/wallet/topup",
        json={"wallet_id": str(WALLET_ID), "psp_token": "tok-1", "amount_minor_units": 5000, "currency": "AED"},
    )
    assert topup_response.status_code == 200
    txn_ref = topup_response.json()["psp_transaction_ref"]

    balance_before = client.get(f"/wallet/{WALLET_ID}/balance")
    assert balance_before.json()["balance_minor_units"] == 0

    webhook_response = client.post(
        "/wallet/topup/webhook",
        json={"wallet_id": str(WALLET_ID), "psp_transaction_id": txn_ref, "amount_minor_units": 5000},
    )
    assert webhook_response.status_code == 200

    balance_after = client.get(f"/wallet/{WALLET_ID}/balance")
    assert balance_after.json()["balance_minor_units"] == 5000


def test_duplicate_webhook_via_http_is_idempotent():
    client = TestClient(_build_app())
    topup_response = client.post(
        "/wallet/topup",
        json={"wallet_id": str(WALLET_ID), "psp_token": "tok-1", "amount_minor_units": 5000, "currency": "AED"},
    )
    txn_ref = topup_response.json()["psp_transaction_ref"]

    for _ in range(3):
        client.post(
            "/wallet/topup/webhook",
            json={"wallet_id": str(WALLET_ID), "psp_transaction_id": txn_ref, "amount_minor_units": 5000},
        )

    balance = client.get(f"/wallet/{WALLET_ID}/balance")
    assert balance.json()["balance_minor_units"] == 5000
