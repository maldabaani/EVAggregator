"""Task 1.1 — FastAPI routes: version negotiation, the 2.1.1 read-only shim
(explicitly rejecting writes with 405), and 2.2.1/2.3.0 Location reads.

Full CPO/eMSP data exchange (Tokens, Sessions, CDRs, push endpoints) is Task
1.2 — this router only proves the version-negotiation and shim-boundary
architecture Task 1.1 owns.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.responses import JSONResponse

from evagg.ocpi.errors import OcpiError, OcpiErrorCode
from evagg.ocpi.locations import LocationRepository
from evagg.ocpi.partner_store import PartnerRegistry
from evagg.ocpi.tariff_bridge import OcpiTariffCatalog
from evagg.ocpi.v211_shim.adapters import location_to_v211, tariff_to_v211
from evagg.ocpi.v221.adapters import location_to_v221, tariff_to_v221
from evagg.ocpi.v230.adapters import location_to_v230, tariff_to_v230
from evagg.ocpi.versions import build_versions_response, negotiate_credentials


def register_ocpi_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(OcpiError)
    async def _handle_ocpi_error(request, exc: OcpiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_response_body())


def build_ocpi_router(
    partner_registry_dependency,
    location_repository_dependency,
    tariff_catalog_dependency,
    base_url: str = "https://api.example.com/ocpi",
) -> APIRouter:
    router = APIRouter(prefix="/ocpi")

    @router.get("/versions")
    async def versions() -> dict:
        return build_versions_response(base_url)

    @router.post("/{version}/credentials")
    async def credentials(
        version: str,
        authorization: str = Header(...),
        registry: PartnerRegistry = Depends(partner_registry_dependency),
    ) -> dict:
        return await negotiate_credentials(registry, authorization, version)

    # --- 2.1.1 shim: read-only ---------------------------------------

    @router.get("/2.1.1/locations")
    async def list_locations_v211(repo: LocationRepository = Depends(location_repository_dependency)) -> dict:
        locations = await repo.list_all()
        return {"data": [location_to_v211(loc).model_dump(mode="json") for loc in locations]}

    @router.get("/2.1.1/locations/{location_id}")
    async def get_location_v211(
        location_id: str, repo: LocationRepository = Depends(location_repository_dependency)
    ) -> dict:
        location = await repo.get(location_id)
        if location is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_LOCATION, f"unknown location: {location_id}")
        return location_to_v211(location).model_dump(mode="json")

    @router.get("/2.1.1/tariffs")
    async def list_tariffs_v211(catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)) -> dict:
        tariffs = await catalog.list_all()
        return {"data": [tariff_to_v211(t).model_dump(mode="json") for t in tariffs]}

    @router.get("/2.1.1/tariffs/{tariff_id}")
    async def get_tariff_v211(
        tariff_id: str, catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)
    ) -> dict:
        tariff = await catalog.get(tariff_id)
        if tariff is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_TARIFF, f"unknown tariff: {tariff_id}")
        return tariff_to_v211(tariff).model_dump(mode="json")

    @router.put("/2.1.1/tokens/{token_uid}")
    @router.patch("/2.1.1/tokens/{token_uid}")
    async def reject_v211_token_write(token_uid: str) -> JSONResponse:
        error = OcpiError(
            OcpiErrorCode.GENERIC_SERVER_ERROR, "the 2.1.1 shim is read-only; token/session mutation is not supported"
        )
        return JSONResponse(status_code=405, content=error.to_response_body())

    @router.put("/2.1.1/sessions/{session_id}")
    @router.patch("/2.1.1/sessions/{session_id}")
    async def reject_v211_session_write(session_id: str) -> JSONResponse:
        error = OcpiError(
            OcpiErrorCode.GENERIC_SERVER_ERROR, "the 2.1.1 shim is read-only; token/session mutation is not supported"
        )
        return JSONResponse(status_code=405, content=error.to_response_body())

    # --- 2.2.1 (primary) ------------------------------------------------

    @router.get("/2.2.1/locations/{location_id}")
    async def get_location_v221(
        location_id: str, repo: LocationRepository = Depends(location_repository_dependency)
    ) -> dict:
        location = await repo.get(location_id)
        if location is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_LOCATION, f"unknown location: {location_id}")
        return location_to_v221(location).model_dump(mode="json")

    @router.get("/2.2.1/tariffs")
    async def list_tariffs_v221(catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)) -> dict:
        tariffs = await catalog.list_all()
        return {"data": [tariff_to_v221(t).model_dump(mode="json") for t in tariffs]}

    @router.get("/2.2.1/tariffs/{tariff_id}")
    async def get_tariff_v221(
        tariff_id: str, catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)
    ) -> dict:
        tariff = await catalog.get(tariff_id)
        if tariff is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_TARIFF, f"unknown tariff: {tariff_id}")
        return tariff_to_v221(tariff).model_dump(mode="json")

    # --- 2.3.0 (forward compatibility) ----------------------------------

    @router.get("/2.3.0/locations/{location_id}")
    async def get_location_v230(
        location_id: str, repo: LocationRepository = Depends(location_repository_dependency)
    ) -> dict:
        location = await repo.get(location_id)
        if location is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_LOCATION, f"unknown location: {location_id}")
        return location_to_v230(location).model_dump(mode="json")

    @router.get("/2.3.0/tariffs")
    async def list_tariffs_v230(catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)) -> dict:
        tariffs = await catalog.list_all()
        return {"data": [tariff_to_v230(t).model_dump(mode="json") for t in tariffs]}

    @router.get("/2.3.0/tariffs/{tariff_id}")
    async def get_tariff_v230(
        tariff_id: str, catalog: OcpiTariffCatalog = Depends(tariff_catalog_dependency)
    ) -> dict:
        tariff = await catalog.get(tariff_id)
        if tariff is None:
            raise OcpiError(OcpiErrorCode.UNKNOWN_TARIFF, f"unknown tariff: {tariff_id}")
        return tariff_to_v230(tariff).model_dump(mode="json")

    return router
