"""Task 5.2 — Autocharge: the charger detects the vehicle's MAC address
locally and sends an OCPP `Authorize` with a synthesized id_tag; the driver
app has no active role at session start, only a confirmation push once the
session begins. Mapping is case-insensitive since MAC addresses arrive from
different hardware/drivers in inconsistent case.
"""

from __future__ import annotations

import uuid
from typing import Protocol


class AutochargeMacStore(Protocol):
    async def get_driver_id_for_mac(self, mac_address: str) -> uuid.UUID | None: ...


class InMemoryAutochargeMacStore:
    def __init__(self) -> None:
        self._mapping: dict[str, uuid.UUID] = {}

    def register(self, mac_address: str, driver_id: uuid.UUID) -> None:
        self._mapping[mac_address.lower()] = driver_id

    async def get_driver_id_for_mac(self, mac_address: str) -> uuid.UUID | None:
        return self._mapping.get(mac_address.lower())


def synthesize_id_tag_for_mac(mac_address: str) -> str:
    return f"AUTOCHARGE:{mac_address.upper()}"
