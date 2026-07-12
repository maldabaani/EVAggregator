"""Structured logging, real dependency health checks, and Prometheus
metrics — none of which existed anywhere in the codebase before this. All
self-hosted: no Sentry/Datadog/etc. account needed for any of it.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as redis_asyncio
from fastapi import APIRouter, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from evagg.core.config import settings

REQUEST_COUNT = Counter(
    "evagg_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "evagg_http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"]
)


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line — the shape any log aggregator (CloudWatch,
    Loki, Datadog) expects without a custom parser."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)
    root.setLevel(level)


class MetricsMiddleware:
    """Records a request counter + latency histogram per (method, route
    path, status) — the route's path template (`/wallet/{wallet_id}/balance`),
    not the raw URL, so metric cardinality doesn't grow with every unique id."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_holder = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        request = Request(scope)
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        REQUEST_COUNT.labels(method=request.method, path=path, status=status_holder["code"]).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(time.monotonic() - start)


def build_metrics_router() -> APIRouter:
    router = APIRouter()

    @router.get("/metrics")
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router


async def _check_postgres() -> tuple[bool, str | None]:
    engine = create_async_engine(settings.migration_database_url, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 - health check must never crash on an unexpected driver error
        return False, str(exc)
    finally:
        await engine.dispose()


async def _check_redis(redis_client: redis_asyncio.Redis) -> tuple[bool, str | None]:
    try:
        await redis_client.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def _check_nats() -> tuple[bool, str | None]:
    import nats

    try:
        nc = await nats.connect(settings.nats_url, connect_timeout=2)
        await nc.close()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def build_healthz_router(redis_client: redis_asyncio.Redis) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz(response: Response) -> dict:
        postgres_ok, postgres_err = await _check_postgres()
        redis_ok, redis_err = await _check_redis(redis_client)
        nats_ok, nats_err = await _check_nats()

        checks = {
            "postgres": {"ok": postgres_ok, **({"error": postgres_err} if postgres_err else {})},
            "redis": {"ok": redis_ok, **({"error": redis_err} if redis_err else {})},
            "nats": {"ok": nats_ok, **({"error": nats_err} if nats_err else {})},
        }
        healthy = postgres_ok and redis_ok and nats_ok
        response.status_code = 200 if healthy else 503
        return {"status": "ok" if healthy else "degraded", "mode": settings.app_mode, "checks": checks}

    return router


def instrument_app(app: FastAPI, redis_client: redis_asyncio.Redis) -> None:
    """Wires metrics middleware + `/metrics` + the real `/healthz` onto an
    already-built app. Call after all business routers are mounted so route
    path templates are resolvable for the metrics middleware."""
    app.add_middleware(MetricsMiddleware)
    app.include_router(build_metrics_router())
    app.include_router(build_healthz_router(redis_client))
