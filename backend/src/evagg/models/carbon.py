"""Grid carbon intensity zone mapping (Task 1.4).

`carbon_zone` is global reference/lookup data shared across all tenants (it
maps country/area codes to a provider's zone id), not tenant business data —
it intentionally has no `tenant_id` and is exempt from the RLS audit
(see `evagg.scripts.audit_rls.EXEMPT_TABLES`).
"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TimestampMixin, UUIDPKMixin


class CarbonZone(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "carbon_zone"
    __table_args__ = (
        UniqueConstraint("country_code", "area_code", name="uq_carbon_zone_country_area"),
    )

    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    area_code: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_zone_id: Mapped[str] = mapped_column(String(50), nullable=False)
