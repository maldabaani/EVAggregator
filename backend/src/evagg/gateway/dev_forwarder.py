"""The forwarding half of Task 6.3's own docstring — "in a real deployment,
forwards authenticated calls to internal services with a signed
`X-Tenant-Id` header" — that `gateway/app.py` never actually built (it only
issues OAuth/PKCE tokens). The portal has no login flow at all: an operator
just types a tenant/team id into a form, so there's no session to derive
trust from. This mounts a small reverse proxy that takes whatever tenant id
the caller states, signs it, and forwards to `evagg.main`.

This is *not* a real gateway forwarder: the "trust boundary" here is
"whatever the caller says the tenant is", which is only acceptable because
this is local dev/testing tooling standing in for a login flow that was
never built — see the module docstring on `evagg.gateway_app` for where
this is (and isn't) mounted.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import FastAPI, Request, Response

from evagg.gateway.trust import SIGNATURE_HEADER, sign_tenant_id

DEV_TENANT_HEADER = "x-dev-tenant-id"
# A plain `<a href>` download (the cost-report CSV export) can't attach a
# custom header — the browser navigates to it directly, bypassing
# HttpClient entirely — so the query param is the only way that link can
# identify its tenant.
DEV_TENANT_QUERY_PARAM = "_dev_tenant_id"

_HOP_BY_HOP_REQUEST_HEADERS = {"host", "content-length", DEV_TENANT_HEADER}
_HOP_BY_HOP_RESPONSE_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def _signed_headers(request: Request, tenant_id: uuid.UUID) -> dict[str, str]:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP_REQUEST_HEADERS}
    headers["x-tenant-id"] = str(tenant_id)
    headers[SIGNATURE_HEADER] = sign_tenant_id(tenant_id)
    return headers


def mount_dev_forwarder(
    app: FastAPI,
    upstream_base_url: str,
    path_prefixes: tuple[str, ...],
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Registers a catch-all proxy route under each of `path_prefixes`.
    Only those prefixes are forwarded — everything else on this app (the
    real OAuth endpoints) is untouched.

    `transport` is exposed purely for tests, so they can point the
    forwarder at an in-process ASGI app (`httpx.ASGITransport`) instead of
    a real socket — production always uses the real one, selected by
    passing `base_url` alone."""
    client = httpx.AsyncClient(base_url=upstream_base_url, transport=transport)

    async def _forward(upstream_path: str, request: Request) -> Response:
        raw_tenant = request.headers.get(DEV_TENANT_HEADER) or request.query_params.get(DEV_TENANT_QUERY_PARAM)
        if not raw_tenant:
            return Response(
                content=b'{"type":"about:blank","title":"X-Dev-Tenant-Id header (or _dev_tenant_id query '
                b'param) required","status":400}',
                status_code=400,
                media_type="application/problem+json",
            )
        try:
            tenant_id = uuid.UUID(raw_tenant)
        except ValueError:
            return Response(
                content=b'{"type":"about:blank","title":"tenant id must be a UUID","status":400}',
                status_code=400,
                media_type="application/problem+json",
            )

        body = await request.body()
        upstream_params = {k: v for k, v in request.query_params.items() if k != DEV_TENANT_QUERY_PARAM}
        upstream_response = await client.request(
            request.method,
            f"/{upstream_path}",
            params=upstream_params,
            content=body,
            headers=_signed_headers(request, tenant_id),
        )
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers={
                k: v for k, v in upstream_response.headers.items() if k.lower() not in _HOP_BY_HOP_RESPONSE_HEADERS
            },
        )

    for prefix in path_prefixes:
        bare_path = prefix.lstrip("/")

        async def forward_with_subpath(path: str, request: Request, _bare=bare_path) -> Response:
            return await _forward(f"{_bare}/{path}", request)

        async def forward_bare(request: Request, _bare=bare_path) -> Response:
            return await _forward(_bare, request)

        app.add_api_route(
            f"{prefix}/{{path:path}}",
            forward_with_subpath,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
        app.add_api_route(
            prefix,
            forward_bare,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
