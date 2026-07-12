"""Task 1.1 — FastAPI routes: version negotiation, the 2.1.1 read-only shim
(explicitly rejecting writes with 405), and 2.2.1/2.3.0 Location reads.

Full CPO/eMSP data exchange (Tokens, Sessions, CDRs, push endpoints) is Task
1.2 — this router only proves the version-negotiation and shim-boundary
architecture Task 1.1 owns.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from evagg.ocpi.charging_preferences import ChargingPreferencesService
from evagg.ocpi.charging_profiles import ChargingProfilePeriod, ChargingProfileService
from evagg.ocpi.commands import OcpiCommandResult, OcpiCommandService
from evagg.ocpi.errors import OcpiError, OcpiErrorCode
from evagg.ocpi.locations import LocationRepository
from evagg.ocpi.partner_store import PartnerRegistry
from evagg.ocpi.tariff_bridge import OcpiTariffCatalog
from evagg.ocpi.v211_shim.adapters import location_to_v211, tariff_to_v211
from evagg.ocpi.v221.adapters import location_to_v221, tariff_to_v221
from evagg.ocpi.v230.adapters import location_to_v230, tariff_to_v230
from evagg.ocpi.versions import build_versions_response, negotiate_credentials


class StartSessionRequest(BaseModel):
    tenant_id: uuid.UUID
    location_id: str
    token_uid: str
    connector_id: int = 1
    response_url: str | None = None


class StopSessionRequest(BaseModel):
    tenant_id: uuid.UUID
    session_id: str
    response_url: str | None = None


class ReserveNowRequest(BaseModel):
    tenant_id: uuid.UUID
    location_id: str
    token_uid: str
    expiry_date: datetime
    reservation_id: str
    connector_id: int = 1
    response_url: str | None = None


class UnlockConnectorRequest(BaseModel):
    tenant_id: uuid.UUID
    location_id: str
    connector_id: int = 1
    response_url: str | None = None


class CancelReservationRequest(BaseModel):
    tenant_id: uuid.UUID
    location_id: str
    reservation_id: str
    response_url: str | None = None


def _command_result_dict(result: OcpiCommandResult) -> dict:
    return {"result": result.result.value, "session_id": result.session_id, "reason": result.reason}


class ChargingPreferencesRequest(BaseModel):
    profile_type: str
    departure_time: datetime | None = None
    energy_need_kwh: float | None = None
    discharge_allowed: bool | None = None


def _charging_preferences_dict(preferences) -> dict | None:
    if preferences is None:
        return None
    return {
        "profile_type": preferences.profile_type,
        "departure_time": preferences.departure_time.isoformat() if preferences.departure_time else None,
        "energy_need_kwh": preferences.energy_need_kwh,
        "discharge_allowed": preferences.discharge_allowed,
    }


class _ChargingProfilePeriodPayload(BaseModel):
    start_period: int
    limit: float


class _ChargingProfilePayload(BaseModel):
    charging_rate_unit: str
    charging_profile_period: list[_ChargingProfilePeriodPayload]
    start_date_time: datetime | None = None
    min_charging_rate: float | None = None


class SetChargingProfileRequest(BaseModel):
    charging_profile: _ChargingProfilePayload
    duration: int | None = None
    response_url: str | None = None


def _active_profile_dict(profile) -> dict | None:
    if profile is None:
        return None
    return {
        "charging_rate_unit": profile.charging_rate_unit,
        "charging_profile_period": [{"start_period": p.start_period, "limit": p.limit} for p in profile.periods],
        "duration": profile.duration,
        "min_charging_rate": profile.min_charging_rate,
        "start_date_time": profile.start_date_time.isoformat() if profile.start_date_time else None,
    }


def register_ocpi_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(OcpiError)
    async def _handle_ocpi_error(request, exc: OcpiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_response_body())


def build_ocpi_router(
    partner_registry_dependency,
    location_repository_dependency,
    tariff_catalog_dependency,
    charging_profile_service_dependency,
    command_service_dependency,
    charging_preferences_service_dependency,
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

    # --- ChargingProfiles (2.2.1+ only — not part of the 2.1.1 module set) --

    async def _put_charging_profile(
        session_id: str, body: SetChargingProfileRequest, service: ChargingProfileService
    ) -> dict:
        periods = [
            ChargingProfilePeriod(start_period=p.start_period, limit=p.limit)
            for p in body.charging_profile.charging_profile_period
        ]
        result = await service.set_charging_profile(
            session_id,
            body.charging_profile.charging_rate_unit,
            periods,
            duration=body.duration,
            min_charging_rate=body.charging_profile.min_charging_rate,
            start_date_time=body.charging_profile.start_date_time,
        )
        return {"result": result.result.value, "reason": result.reason}

    async def _get_charging_profile(session_id: str, service: ChargingProfileService) -> dict:
        status, profile = await service.get_active_profile(session_id)
        return {"result": status.value, "profile": _active_profile_dict(profile)}

    @router.put("/2.2.1/chargingprofiles/{session_id}")
    async def put_charging_profile_v221(
        session_id: str,
        body: SetChargingProfileRequest,
        service: ChargingProfileService = Depends(charging_profile_service_dependency),
    ) -> dict:
        return await _put_charging_profile(session_id, body, service)

    @router.get("/2.2.1/chargingprofiles/{session_id}")
    async def get_charging_profile_v221(
        session_id: str, service: ChargingProfileService = Depends(charging_profile_service_dependency)
    ) -> dict:
        return await _get_charging_profile(session_id, service)

    @router.put("/2.3.0/chargingprofiles/{session_id}")
    async def put_charging_profile_v230(
        session_id: str,
        body: SetChargingProfileRequest,
        service: ChargingProfileService = Depends(charging_profile_service_dependency),
    ) -> dict:
        return await _put_charging_profile(session_id, body, service)

    @router.get("/2.3.0/chargingprofiles/{session_id}")
    async def get_charging_profile_v230(
        session_id: str, service: ChargingProfileService = Depends(charging_profile_service_dependency)
    ) -> dict:
        return await _get_charging_profile(session_id, service)

    # --- Commands (2.2.1+ only — not part of the 2.1.1 module set) ---------

    def _register_commands(version: str) -> None:
        @router.post(f"/{version}/commands/START_SESSION", name=f"start_session_{version}")
        async def start_session(
            body: StartSessionRequest, service: OcpiCommandService = Depends(command_service_dependency)
        ) -> dict:
            result = await service.start_session(body.location_id, body.tenant_id, body.token_uid, body.connector_id)
            return _command_result_dict(result)

        @router.post(f"/{version}/commands/STOP_SESSION", name=f"stop_session_{version}")
        async def stop_session(
            body: StopSessionRequest, service: OcpiCommandService = Depends(command_service_dependency)
        ) -> dict:
            result = await service.stop_session(body.session_id, body.tenant_id)
            return _command_result_dict(result)

        @router.post(f"/{version}/commands/RESERVE_NOW", name=f"reserve_now_{version}")
        async def reserve_now(
            body: ReserveNowRequest, service: OcpiCommandService = Depends(command_service_dependency)
        ) -> dict:
            result = await service.reserve_now(
                body.location_id, body.tenant_id, body.token_uid, body.expiry_date, body.reservation_id,
                body.connector_id,
            )
            return _command_result_dict(result)

        @router.post(f"/{version}/commands/UNLOCK_CONNECTOR", name=f"unlock_connector_{version}")
        async def unlock_connector(
            body: UnlockConnectorRequest, service: OcpiCommandService = Depends(command_service_dependency)
        ) -> dict:
            result = await service.unlock_connector(body.location_id, body.tenant_id, body.connector_id)
            return _command_result_dict(result)

        @router.post(f"/{version}/commands/CANCEL_RESERVATION", name=f"cancel_reservation_{version}")
        async def cancel_reservation(
            body: CancelReservationRequest, service: OcpiCommandService = Depends(command_service_dependency)
        ) -> dict:
            result = await service.cancel_reservation(body.location_id, body.tenant_id, body.reservation_id)
            return _command_result_dict(result)

    _register_commands("2.2.1")
    _register_commands("2.3.0")

    # --- Charging Preferences (2.2.1+ only) ---------------------------------

    def _register_charging_preferences(version: str) -> None:
        @router.put(f"/{version}/sessions/{{session_id}}/charging_preferences", name=f"set_charging_prefs_{version}")
        async def set_charging_preferences(
            session_id: str,
            body: ChargingPreferencesRequest,
            service: ChargingPreferencesService = Depends(charging_preferences_service_dependency),
        ) -> dict:
            result = await service.set_charging_preferences(
                session_id, body.profile_type, body.departure_time, body.energy_need_kwh, body.discharge_allowed
            )
            return {"result": result.value}

        @router.get(f"/{version}/sessions/{{session_id}}/charging_preferences", name=f"get_charging_prefs_{version}")
        async def get_charging_preferences(
            session_id: str,
            service: ChargingPreferencesService = Depends(charging_preferences_service_dependency),
        ) -> dict:
            preferences = await service.get_charging_preferences(session_id)
            return {"preferences": _charging_preferences_dict(preferences)}

    _register_charging_preferences("2.2.1")
    _register_charging_preferences("2.3.0")

    return router
