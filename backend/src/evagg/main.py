"""FastAPI app entrypoint.

Minimal skeleton for now — the full API Gateway/BFF split (auth, rate
limiting, SSO) lands in Task 6.3. This wires the tenant-context middleware
(Task 4.1) so every route from here on is tenant-scoped by construction.
"""

from __future__ import annotations

from fastapi import FastAPI

from evagg.core.tenancy import TenantContextMiddleware

app = FastAPI(title="EV Charging Aggregator Platform API", version="0.1.0")
app.add_middleware(TenantContextMiddleware)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
