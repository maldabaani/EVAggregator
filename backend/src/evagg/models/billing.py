"""Billing: tariffs, versioning, wallet/ledger, payment methods, promotions,
B2B invoicing and payouts.

All monetary columns are integer minor units (fils/cents) per engineering
standards — never float.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class Tariff(Base, TenantScopedMixin):
    __tablename__ = "tariff"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217


class TariffComponent(Base, TenantScopedMixin):
    __tablename__ = "tariff_component"

    tariff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tariff.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'energy'|'time'|'flat'|'idle'
    price_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    step_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    applies_after_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # idle only


class TariffVersion(Base, TenantScopedMixin):
    """A session is always billed against the version active at its
    start_timestamp, never the latest — see Task 3.2."""

    __tablename__ = "tariff_version"

    tariff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tariff.id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Wallet(Base, TenantScopedMixin):
    __tablename__ = "wallet"

    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.id"), nullable=False, unique=True, index=True
    )
    balance_minor_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class WalletLedger(Base, TenantScopedMixin):
    """Append-only. `wallet.balance_minor_units` is a derived/cached value —
    this table is the source of truth (see Task 3.3)."""

    __tablename__ = "wallet_ledger"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet.id"), nullable=False, index=True
    )
    amount_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'topup'|'charge_deduction'|'refund'
    reference_id: Mapped[str] = mapped_column(String(255), nullable=False)  # PSP txn id / session id, idempotency key


class PaymentMethod(Base, TenantScopedMixin):
    __tablename__ = "payment_method"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'wallet_balance'|'direct_card'
    psp_token: Mapped[str | None] = mapped_column(String(255), nullable=True)  # never a raw PAN
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)


class Promotion(Base, TenantScopedMixin):
    __tablename__ = "promotion"

    code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # null => seasonal, auto-applied
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'percent'|'flat'
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # percent*100 or minor units, per discount_type
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=True, index=True
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class PromotionRedemption(Base, TenantScopedMixin):
    __tablename__ = "promotion_redemption"
    __table_args__ = (
        UniqueConstraint("promotion_id", "session_id", name="uq_promotion_redemption_promotion_session"),
    )

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promotion.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


class Invoice(Base, TenantScopedMixin):
    __tablename__ = "invoice"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # 'draft'|'issued'|'paid'|'overdue'
    total_minor_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class InvoiceAdjustment(Base, TenantScopedMixin):
    """Corrections to an issued (immutable) invoice via linked credit note."""

    __tablename__ = "invoice_adjustment"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice.id"), nullable=False, index=True
    )
    amount_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)  # signed delta
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class PayoutRule(Base, TenantScopedMixin):
    __tablename__ = "payout_rule"

    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=True, index=True
    )
    split_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'percent'|'flat_fee'
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class Payout(Base, TenantScopedMixin):
    __tablename__ = "payout"

    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
