import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.reservation_router import build_reservation_router
from evagg.driver_app.reservations import Reservation, ReservationError, ReservationNotFoundError
from evagg.gateway.jwt_tokens import create_access_token

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
EXPIRES_AT = datetime.now(timezone.utc) + timedelta(hours=1)


class _FakeService:
    def __init__(self, reservation=None, error=None, listing=None):
        self.reservation = reservation
        self.error = error
        self.listing = listing or []
        self.last_reserve_call = None
        self.last_cancel_call = None

    async def reserve(self, charger_id, connector_id, expires_at, driver_id, tenant_id):
        self.last_reserve_call = (charger_id, connector_id, driver_id, tenant_id)
        if self.error:
            raise self.error
        return self.reservation

    async def list_for_driver(self, driver_id):
        return self.listing

    async def cancel(self, reservation_id, driver_id, tenant_id):
        self.last_cancel_call = (reservation_id, driver_id, tenant_id)
        if self.error:
            raise self.error


def _build_app(service):
    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_reservation_router(get_service))
    return app


def _auth_header():
    return {"Authorization": f"Bearer {create_access_token(str(DRIVER_ID), TENANT_ID)}"}


def test_create_reservation_requires_a_bearer_token():
    app = _build_app(_FakeService())
    client = TestClient(app)

    response = client.post(
        "/driver/reservations", json={"charger_id": "CP-1", "expires_at": EXPIRES_AT.isoformat()}
    )

    assert response.status_code == 401


def test_a_successful_reservation_returns_its_shape():
    reservation = Reservation(id="r-1", charger_id="CP-1", connector_id=1, expires_at=EXPIRES_AT)
    app = _build_app(_FakeService(reservation=reservation))
    client = TestClient(app)

    response = client.post(
        "/driver/reservations",
        json={"charger_id": "CP-1", "expires_at": EXPIRES_AT.isoformat()},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["id"] == "r-1"


def test_a_rejected_reservation_returns_400():
    app = _build_app(_FakeService(error=ReservationError("charger offline")))
    client = TestClient(app)

    response = client.post(
        "/driver/reservations",
        json={"charger_id": "CP-1", "expires_at": EXPIRES_AT.isoformat()},
        headers=_auth_header(),
    )

    assert response.status_code == 400


def test_list_reservations_returns_the_drivers_own_reservations():
    reservation = Reservation(id="r-1", charger_id="CP-1", connector_id=1, expires_at=EXPIRES_AT)
    app = _build_app(_FakeService(listing=[reservation]))
    client = TestClient(app)

    response = client.get("/driver/reservations", headers=_auth_header())

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "r-1"


def test_cancel_a_reservation_succeeds():
    app = _build_app(_FakeService())
    client = TestClient(app)

    response = client.delete("/driver/reservations/r-1", headers=_auth_header())

    assert response.status_code == 204


def test_cancel_an_unowned_or_unknown_reservation_returns_404():
    app = _build_app(_FakeService(error=ReservationNotFoundError("r-1")))
    client = TestClient(app)

    response = client.delete("/driver/reservations/r-1", headers=_auth_header())

    assert response.status_code == 404
