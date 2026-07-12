"""Task 3.1 — tariff save validation: at least one energy or time component
is required (a tariff that's pure flat/idle fees can't actually price a
charging session), and every component's step_size must be > 0.
"""

from __future__ import annotations

from evagg.billing.tariff_calculator import TariffComponentInput


class TariffValidationError(Exception):
    pass


def validate_tariff_components(components: list[TariffComponentInput]) -> None:
    if not any(component.type in ("energy", "time") for component in components):
        raise TariffValidationError("tariff must include at least one energy or time component")

    for component in components:
        if component.step_size <= 0:
            raise TariffValidationError(f"step_size must be > 0 (component type={component.type})")
