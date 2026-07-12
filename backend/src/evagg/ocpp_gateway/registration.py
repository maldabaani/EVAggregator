"""Charger registration state (Task 2.1's boot-notification idempotency, and
the foundation Task 2.2's full BootNotification handler builds on).

A duplicate `BootNotification` from an already-known charger only refreshes
`last_boot_at` (and vendor/model/firmware, in case of an FW update) — it must
never recreate the charger row or reset its registration `status`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class BootResult:
    status: str  # 'pending' | 'accepted' | 'rejected'
    is_new_charger: bool


class ChargerRegistry(Protocol):
    async def upsert_on_boot(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        vendor: str | None,
        model: str | None,
        firmware_version: str | None,
    ) -> BootResult: ...


class InMemoryChargerRegistry:
    """Reference implementation for unit tests. Production implementation
    upserts against the `charger` table (Task 6.1) inside the request's
    tenant-scoped session."""

    def __init__(self) -> None:
        self._chargers: dict[str, dict] = {}

    async def upsert_on_boot(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        vendor: str | None,
        model: str | None,
        firmware_version: str | None,
    ) -> BootResult:
        existing = self._chargers.get(charger_id)
        if existing is None:
            self._chargers[charger_id] = {
                "tenant_id": tenant_id,
                "vendor": vendor,
                "model": model,
                "firmware_version": firmware_version,
                "status": "pending",
                "last_boot_at": time.time(),
            }
            return BootResult(status="pending", is_new_charger=True)

        existing["vendor"] = vendor
        existing["model"] = model
        existing["firmware_version"] = firmware_version
        existing["last_boot_at"] = time.time()
        return BootResult(status=existing["status"], is_new_charger=False)

    def set_status(self, charger_id: str, status: str) -> None:
        """Test/ops helper — simulates an admin approving a pending charger."""
        self._chargers[charger_id]["status"] = status
