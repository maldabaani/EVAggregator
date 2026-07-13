"""Forwards driver-authenticated `/wallet/*` calls from `evagg.edge_app` to
`evagg.main`'s tenant-gated wallet/payment-method routes, the same
JWT-verified-then-signed pattern as
`evagg.driver_app.session_start_forwarder`.

The mobile-facing paths here (`/wallet/balance`, `/wallet/topup`,
`/wallet/payment-method`) deliberately carry no `wallet_id` at all —
unlike `evagg.billing.wallet_router`'s own routes, which take a
caller-supplied `wallet_id` with no ownership check whatsoever (anyone
who can reach `evagg.main` could read or top up any wallet just by
guessing an id). This forwarder always substitutes the verified driver's
own id for the upstream `wallet_id`, so a driver can only ever act on
their own wallet — matching the `wallet_id_for_driver` convention already
used to resolve a driver's payment method at session-start time
(composition.py: `wallet_id_for_driver=lambda driver_id: driver_id`).
"""

from __future__ import annotations

import json

import httpx
from fastapi import Depends, FastAPI, Request, Response

from evagg.gateway.trust import SIGNATURE_HEADER, sign_tenant_id
from evagg.identity.driver_session import DriverIdentity, require_driver_identity


def mount_wallet_forwarder(
    app: FastAPI,
    upstream_base_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    client = httpx.AsyncClient(base_url=upstream_base_url, transport=transport)

    def _headers(identity: DriverIdentity) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-tenant-id": str(identity.tenant_id),
            SIGNATURE_HEADER: sign_tenant_id(identity.tenant_id),
        }

    def _relay(upstream_response: httpx.Response) -> Response:
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    async def get_balance(identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        upstream_response = await client.get(
            f"/wallet/{identity.driver_id}/balance", headers=_headers(identity)
        )
        return _relay(upstream_response)

    async def topup(request: Request, identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        raw_body = await request.body()
        payload = json.loads(raw_body) if raw_body else {}
        payload["wallet_id"] = str(identity.driver_id)
        upstream_response = await client.post(
            "/wallet/topup", content=json.dumps(payload).encode("utf-8"), headers=_headers(identity)
        )
        return _relay(upstream_response)

    async def get_payment_method(identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        upstream_response = await client.get(
            f"/wallet/{identity.driver_id}/payment-method", headers=_headers(identity)
        )
        return _relay(upstream_response)

    async def set_payment_method(request: Request, identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        raw_body = await request.body()
        upstream_response = await client.post(
            f"/wallet/{identity.driver_id}/payment-method", content=raw_body, headers=_headers(identity)
        )
        return _relay(upstream_response)

    app.add_api_route("/wallet/balance", get_balance, methods=["GET"], include_in_schema=False)
    app.add_api_route("/wallet/topup", topup, methods=["POST"], include_in_schema=False)
    app.add_api_route("/wallet/payment-method", get_payment_method, methods=["GET"], include_in_schema=False)
    app.add_api_route("/wallet/payment-method", set_payment_method, methods=["POST"], include_in_schema=False)
