"""Forwards driver-authenticated `/charging/session/*` calls (start, status,
stop) from `evagg.edge_app` (where a driver connects, authenticated by
their own JWT, not a tenant header) to `evagg.main`'s tenant-gated routes,
where `SessionStartService` actually lives — a separate process in
production (`backend-main`), reached over real HTTP.

The status/stop routes also always inject the token's own driver_id
(as a query param / body field respectively) rather than trusting a
client-supplied one — `SessionStartService` uses it to refuse a driver
who isn't the one who started that session.

Unlike `evagg.gateway.dev_forwarder` (which trusts whatever tenant id the
caller declares — acceptable only for local portal dev, standing in for a
login flow that was never built there), the tenant id signed here comes
from the driver's own verified access token, so a driver can never claim a
tenant they don't belong to.

The `qr` and `app` methods' request bodies carry a `driver_id` field that is
likewise always overwritten with the token's own subject before
forwarding, rather than trusting whatever the client sent — otherwise a
valid driver token would let its holder start a session *as a different
driver* just by editing the JSON body. `autocharge`/`plug-and-charge`
resolve their own driver identity server-side (from a registered MAC
address or vehicle certificate) and carry no such field.
"""

from __future__ import annotations

import json

import httpx
from fastapi import Depends, FastAPI, Request, Response

from evagg.gateway.trust import SIGNATURE_HEADER, sign_tenant_id
from evagg.identity.driver_session import DriverIdentity, require_driver_identity

_FORWARDED_METHODS = ("qr", "autocharge", "plug-and-charge", "app")
_METHODS_WITH_DRIVER_ID_IN_BODY = ("qr", "app")


def mount_session_start_forwarder(
    app: FastAPI,
    upstream_base_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    client = httpx.AsyncClient(base_url=upstream_base_url, transport=transport)

    async def forward(
        method: str,
        request: Request,
        identity: DriverIdentity = Depends(require_driver_identity),
    ) -> Response:
        if method not in _FORWARDED_METHODS:
            return Response(status_code=404)

        raw_body = await request.body()
        if method in _METHODS_WITH_DRIVER_ID_IN_BODY:
            payload = json.loads(raw_body) if raw_body else {}
            payload["driver_id"] = str(identity.driver_id)
            raw_body = json.dumps(payload).encode("utf-8")

        upstream_response = await client.post(
            f"/charging/session/start/{method}",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "x-tenant-id": str(identity.tenant_id),
                SIGNATURE_HEADER: sign_tenant_id(identity.tenant_id),
            },
        )
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    async def forward_status(
        session_id: str,
        identity: DriverIdentity = Depends(require_driver_identity),
    ) -> Response:
        upstream_response = await client.get(
            f"/charging/session/{session_id}/status",
            params={"driver_id": str(identity.driver_id)},
            headers={
                "x-tenant-id": str(identity.tenant_id),
                SIGNATURE_HEADER: sign_tenant_id(identity.tenant_id),
            },
        )
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    async def forward_stop(
        session_id: str,
        identity: DriverIdentity = Depends(require_driver_identity),
    ) -> Response:
        upstream_response = await client.post(
            f"/charging/session/{session_id}/stop",
            json={"driver_id": str(identity.driver_id)},
            headers={
                "x-tenant-id": str(identity.tenant_id),
                SIGNATURE_HEADER: sign_tenant_id(identity.tenant_id),
            },
        )
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    app.add_api_route(
        "/charging/session/start/{method}",
        forward,
        methods=["POST"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/charging/session/{session_id}/status",
        forward_status,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/charging/session/{session_id}/stop",
        forward_stop,
        methods=["POST"],
        include_in_schema=False,
    )
