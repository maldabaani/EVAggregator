"""Real Stripe webhook signature verification (the `Stripe-Signature` header
scheme Stripe documents at https://stripe.com/docs/webhooks#verify-manually),
plus the adapter endpoint that turns a real Stripe `payment_intent.succeeded`
event into a call against the existing internal `WalletService.
handle_topup_webhook` — this is the piece `StripePaymentProvider` was
missing: it sends the charge request, but nothing received the async
confirmation.

Verification itself doesn't depend on `app_mode` — the same code path runs
in both. What differs is where a validly-signed payload comes from: a real
Stripe account posts one in production; `build_test_signature` (below)
constructs one locally for testing mode / local demos, using the same
`stripe_webhook_secret` `MockPaymentProvider` and this module both know.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from evagg.billing.wallet import WalletService


class StripeWebhookError(Exception):
    pass


def build_test_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Builds a valid `Stripe-Signature` header value for a given payload —
    exactly what Stripe's own servers compute, used here so testing mode /
    local demos can prove the verification path works without a real
    Stripe account posting to us."""
    timestamp = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def verify_stripe_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> None:
    """Raises `StripeWebhookError` unless `sig_header` is a valid, recent
    signature of `payload` under `secret`. Constant-time comparison guards
    against timing attacks on the signature check itself."""
    parts = dict(part.split("=", 1) for part in sig_header.split(",") if "=" in part)
    if "t" not in parts or "v1" not in parts:
        raise StripeWebhookError("malformed Stripe-Signature header")

    try:
        timestamp = int(parts["t"])
    except ValueError as exc:
        raise StripeWebhookError("malformed timestamp in Stripe-Signature header") from exc

    now = now if now is not None else time.time()
    if abs(now - timestamp) > tolerance_seconds:
        raise StripeWebhookError("Stripe-Signature timestamp outside tolerance window")

    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts["v1"]):
        raise StripeWebhookError("signature mismatch")


def build_stripe_webhook_router(service_dependency, webhook_secret: str) -> APIRouter:
    router = APIRouter(prefix="/billing/stripe", tags=["billing"])

    @router.post("/webhook")
    async def stripe_webhook(request: Request, service: WalletService = Depends(service_dependency)) -> dict:
        sig_header = request.headers.get("stripe-signature")
        if not sig_header:
            raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

        payload = await request.body()
        try:
            verify_stripe_signature(payload, sig_header, webhook_secret)
        except StripeWebhookError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        event = await request.json()
        if event.get("type") != "payment_intent.succeeded":
            return {"status": "ignored", "type": event.get("type")}

        intent = event.get("data", {}).get("object", {})
        raw_wallet_id = intent.get("metadata", {}).get("wallet_id")
        if not raw_wallet_id:
            raise HTTPException(status_code=400, detail="payment_intent missing metadata.wallet_id")

        try:
            wallet_id = uuid.UUID(raw_wallet_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="metadata.wallet_id is not a valid UUID") from exc

        await service.handle_topup_webhook(wallet_id, intent["id"], intent["amount"])
        return {"status": "ok"}

    return router
