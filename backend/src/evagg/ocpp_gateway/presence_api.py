"""Task 2.4 — consumer-facing presence read API (map/list views, etc.).

The registry itself and its write path (`mark_online`/`refresh`/`mark_offline`)
are Task 2.1's; this module is purely the read side, including the bulk
lookup used by map/list views so they don't issue one request per charger.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from evagg.ocpp_gateway.presence import PresenceRegistry, PresenceState


async def get_presence(charger_id: str, registry: PresenceRegistry) -> PresenceState | None:
    return await registry.get(charger_id)


async def get_bulk_presence(charger_ids: list[str], registry: PresenceRegistry) -> dict[str, PresenceState | None]:
    return {charger_id: await registry.get(charger_id) for charger_id in charger_ids}


def build_presence_router(registry_dependency) -> APIRouter:
    """Factory so the router can be wired to whichever PresenceRegistry
    instance the app is configured with (Redis in production, in-memory in
    tests) via FastAPI's dependency injection."""
    router = APIRouter(prefix="/internal/chargers", tags=["presence"])

    @router.get("/presence")
    async def bulk_presence(
        ids: list[str] = Query(...), registry: PresenceRegistry = Depends(registry_dependency)
    ) -> dict[str, dict | None]:
        states = await get_bulk_presence(ids, registry)
        return {charger_id: (state.__dict__ if state else None) for charger_id, state in states.items()}

    @router.get("/{charger_id}/presence")
    async def single_presence(
        charger_id: str, registry: PresenceRegistry = Depends(registry_dependency)
    ) -> dict | None:
        state = await get_presence(charger_id, registry)
        return state.__dict__ if state else None

    return router
