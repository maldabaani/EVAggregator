"""Task 3.1 — pure tariff cost calculation. No DB/network here so both the
admin preview endpoint and the nightly billing job (Task 3.3) can share this
exact logic without drifting apart.

Idle fee grace period: `applies_after_minutes` is read at billing time, not
baked into the tariff at creation time — a session shorter than the grace
period contributes $0 idle cost regardless of how long the idle component's
own step accounting would otherwise imply.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TariffComponentInput:
    type: str  # 'energy' | 'time' | 'flat' | 'idle'
    price_minor_units: int
    step_size: int = 1
    applies_after_minutes: int | None = None  # idle only


def calculate_session_cost(
    components: list[TariffComponentInput],
    duration_minutes: float,
    kwh: float,
    idle_minutes: float = 0.0,
) -> int:
    """Returns the total session cost in integer minor units."""
    total = 0
    for component in components:
        if component.type == "energy":
            total += _proportional_cost(kwh, component.step_size, component.price_minor_units)
        elif component.type == "time":
            total += _proportional_cost(duration_minutes, component.step_size, component.price_minor_units)
        elif component.type == "flat":
            total += component.price_minor_units
        elif component.type == "idle":
            grace_minutes = component.applies_after_minutes or 0
            billable_idle_minutes = max(0.0, idle_minutes - grace_minutes)
            total += _proportional_cost(billable_idle_minutes, component.step_size, component.price_minor_units)
        else:
            raise ValueError(f"unknown tariff component type: {component.type}")
    return total


def _proportional_cost(quantity: float, step_size: int, price_minor_units: int) -> int:
    if step_size <= 0:
        raise ValueError("step_size must be > 0")
    units = quantity / step_size
    return round(units * price_minor_units)
