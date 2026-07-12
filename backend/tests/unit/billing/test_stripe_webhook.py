import json
import uuid

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.billing.stripe_webhook import (
    StripeWebhookError,
    build_stripe_webhook_router,
    build_test_signature,
    verify_stripe_signature,
)
from evagg.billing.wallet import InMemoryWalletLedgerStore, WalletService
from evagg.billing.payment_provider import StubPaymentProvider

WEBHOOK_SECRET = "whsec_test_secret"
WALLET_ID = uuid.uuid4()


def _build_app():
    ledger = InMemoryWalletLedgerStore()
    service = WalletService(ledger, StubPaymentProvider())

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_stripe_webhook_router(get_service, WEBHOOK_SECRET))
    return app, service


def _event_payload(wallet_id: uuid.UUID, amount: int, txn_id: str = "pi_123") -> bytes:
    return json.dumps(
        {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": txn_id, "amount": amount, "metadata": {"wallet_id": str(wallet_id)}}},
        }
    ).encode()


def test_verify_stripe_signature_accepts_valid_signature():
    payload = b'{"hello": "world"}'
    sig = build_test_signature(payload, WEBHOOK_SECRET, timestamp=1_700_000_000)
    verify_stripe_signature(payload, sig, WEBHOOK_SECRET, now=1_700_000_010)


def test_verify_stripe_signature_rejects_tampered_payload():
    payload = b'{"hello": "world"}'
    sig = build_test_signature(payload, WEBHOOK_SECRET, timestamp=1_700_000_000)
    with pytest.raises(StripeWebhookError, match="mismatch"):
        verify_stripe_signature(b'{"hello": "mallory"}', sig, WEBHOOK_SECRET, now=1_700_000_010)


def test_verify_stripe_signature_rejects_stale_timestamp():
    payload = b'{"hello": "world"}'
    sig = build_test_signature(payload, WEBHOOK_SECRET, timestamp=1_700_000_000)
    with pytest.raises(StripeWebhookError, match="tolerance"):
        verify_stripe_signature(payload, sig, WEBHOOK_SECRET, now=1_700_000_000 + 10_000)


def test_verify_stripe_signature_rejects_wrong_secret():
    payload = b'{"hello": "world"}'
    sig = build_test_signature(payload, "whsec_other", timestamp=1_700_000_000)
    with pytest.raises(StripeWebhookError, match="mismatch"):
        verify_stripe_signature(payload, sig, WEBHOOK_SECRET, now=1_700_000_010)


def test_webhook_endpoint_credits_wallet_on_valid_signed_event():
    app, service = _build_app()
    client = TestClient(app)

    payload = _event_payload(WALLET_ID, amount=2500)
    sig = build_test_signature(payload, WEBHOOK_SECRET)

    response = client.post(
        "/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_endpoint_actually_credits_the_ledger():
    app, service = _build_app()
    client = TestClient(app)

    payload = _event_payload(WALLET_ID, amount=2500)
    sig = build_test_signature(payload, WEBHOOK_SECRET)
    client.post(
        "/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )

    assert await service.get_balance(WALLET_ID) == 2500


def test_webhook_endpoint_rejects_bad_signature():
    app, _ = _build_app()
    client = TestClient(app)

    payload = _event_payload(WALLET_ID, amount=2500)
    response = client.post(
        "/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert response.status_code == 400


def test_webhook_endpoint_ignores_unhandled_event_types():
    app, _ = _build_app()
    client = TestClient(app)

    payload = json.dumps({"type": "payment_intent.created", "data": {"object": {}}}).encode()
    sig = build_test_signature(payload, WEBHOOK_SECRET)
    response = client.post(
        "/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_endpoint_rejects_missing_wallet_metadata():
    app, _ = _build_app()
    client = TestClient(app)

    payload = json.dumps(
        {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_1", "amount": 100, "metadata": {}}}}
    ).encode()
    sig = build_test_signature(payload, WEBHOOK_SECRET)
    response = client.post(
        "/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )
    assert response.status_code == 400
