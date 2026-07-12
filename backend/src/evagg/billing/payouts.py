"""Task 3.4 — payout split calculation for independent network operators.
`value` for `percent` is basis points out of 10000 (never a float), matching
the convention already used for promotion discounts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class PayoutRule:
    operator_id: uuid.UUID
    site_id: uuid.UUID | None
    split_type: str  # 'percent' | 'flat_fee'
    value: int


def calculate_payout(gross_revenue_minor_units: int, rule: PayoutRule) -> int:
    if rule.split_type == "percent":
        return round(gross_revenue_minor_units * rule.value / 10_000)
    if rule.split_type == "flat_fee":
        return rule.value
    raise ValueError(f"unknown split_type: {rule.split_type}")
