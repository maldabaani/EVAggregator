"""Exercises the real httpx request/response/retry machinery via
`httpx.MockTransport` — same approach as `tests/unit/carbon/test_provider.py`."""

from __future__ import annotations

import httpx
import pytest

from evagg.billing.payment_provider import PaymentProviderError, StripePaymentProvider


@pytest.mark.asyncio
async def test_successful_charge_returns_psp_transaction_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk_test_123"
        return httpx.Response(200, json={"id": "pi_abc123", "status": "succeeded"})

    provider = StripePaymentProvider(
        api_key="sk_test_123", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    txn_id = await provider.charge("pm_card_visa", 1234, "AED", "session:abc")

    assert txn_id == "pi_abc123"


@pytest.mark.asyncio
async def test_idempotency_key_and_charge_params_are_forwarded():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["idempotency_key"] = request.headers["Idempotency-Key"]
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"id": "pi_x", "status": "succeeded"})

    provider = StripePaymentProvider(
        api_key="sk_test_123", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    await provider.charge("pm_card_visa", 500, "USD", "session:xyz")

    assert captured["idempotency_key"] == "session:xyz"
    assert "amount=500" in captured["body"]
    assert "currency=usd" in captured["body"]
    assert "payment_method=pm_card_visa" in captured["body"]


@pytest.mark.asyncio
async def test_card_declined_raises_immediately_without_retry():
    attempt_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_count["n"] += 1
        return httpx.Response(402, json={"error": {"message": "Your card was declined."}})

    provider = StripePaymentProvider(
        api_key="sk_test_123",
        max_attempts=3,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(PaymentProviderError, match="declined"):
        await provider.charge("pm_card_declined", 1000, "AED", "session:decline")

    assert attempt_count["n"] == 1  # a definitive decline is never retried


@pytest.mark.asyncio
async def test_retries_transient_5xx_before_succeeding():
    attempt_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "pi_after_retry", "status": "succeeded"})

    provider = StripePaymentProvider(
        api_key="sk_test_123",
        max_attempts=3,
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    txn_id = await provider.charge("pm_card_visa", 1000, "AED", "session:retry")

    assert txn_id == "pi_after_retry"
    assert attempt_count["n"] == 3


@pytest.mark.asyncio
async def test_exhausting_retries_on_persistent_5xx_raises_payment_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    provider = StripePaymentProvider(
        api_key="sk_test_123",
        max_attempts=2,
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(PaymentProviderError):
        await provider.charge("pm_card_visa", 1000, "AED", "session:down")


@pytest.mark.asyncio
async def test_malformed_response_body_raises_payment_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = StripePaymentProvider(
        api_key="sk_test_123",
        max_attempts=1,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(PaymentProviderError):
        await provider.charge("pm_card_visa", 1000, "AED", "session:malformed")


@pytest.mark.asyncio
async def test_unexpected_payment_intent_status_raises_payment_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "pi_x", "status": "requires_payment_method"})

    provider = StripePaymentProvider(
        api_key="sk_test_123",
        max_attempts=1,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(PaymentProviderError, match="requires_payment_method"):
        await provider.charge("pm_card_visa", 1000, "AED", "session:bad-status")
