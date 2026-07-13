"""Forwards driver-authenticated `/driver/rewards*` calls from
`evagg.edge_app` to `evagg.main`'s `rewards_router.py`, the same
JWT-verified-then-signed pattern as `session_start_forwarder`/
`wallet_forwarder`. `driver_id` is always substituted with the caller's
verified identity (query param for the GET, body field for the POST) —
never trusted from the client — so a driver can only ever see or redeem
against their own points balance.
"""

from __future__ import annotations

import json

import httpx
from fastapi import Depends, FastAPI, Request, Response

from evagg.gateway.trust import SIGNATURE_HEADER, sign_tenant_id
from evagg.identity.driver_session import DriverIdentity, require_driver_identity


def mount_rewards_forwarder(
    app: FastAPI,
    upstream_base_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    client = httpx.AsyncClient(base_url=upstream_base_url, transport=transport)

    def _signed_headers(identity: DriverIdentity) -> dict[str, str]:
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

    async def get_rewards(identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        upstream_response = await client.get(
            "/driver/rewards",
            params={"driver_id": str(identity.driver_id)},
            headers=_signed_headers(identity),
        )
        return _relay(upstream_response)

    async def redeem(request: Request, identity: DriverIdentity = Depends(require_driver_identity)) -> Response:
        raw_body = await request.body()
        payload = json.loads(raw_body) if raw_body else {}
        payload["driver_id"] = str(identity.driver_id)
        upstream_response = await client.post(
            "/driver/rewards/redeem",
            content=json.dumps(payload).encode("utf-8"),
            headers=_signed_headers(identity),
        )
        return _relay(upstream_response)

    app.add_api_route("/driver/rewards", get_rewards, methods=["GET"], include_in_schema=False)
    app.add_api_route("/driver/rewards/redeem", redeem, methods=["POST"], include_in_schema=False)
