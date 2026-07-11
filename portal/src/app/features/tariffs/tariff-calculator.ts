import { SampleSession, TariffComponentForm } from '../../core/models/tariff.model';

/**
 * Mirrors the backend's `evagg.billing.tariff_calculator.calculate_session_cost`
 * exactly, so the builder's live preview (no round-trip per keystroke) never
 * drifts from what the saved tariff's `/preview` endpoint would return. Kept
 * as a pure function for the same reason the backend one is: easy to unit
 * test in isolation and easy to keep the two in sync deliberately.
 */
export function calculateSessionCost(components: TariffComponentForm[], session: SampleSession): number {
  let total = 0;

  for (const component of components) {
    switch (component.type) {
      case 'energy':
        total += proportionalCost(session.kwh, component.stepSize, component.priceMinorUnits);
        break;
      case 'time':
        total += proportionalCost(session.durationMinutes, component.stepSize, component.priceMinorUnits);
        break;
      case 'flat':
        total += component.priceMinorUnits;
        break;
      case 'idle': {
        const grace = component.appliesAfterMinutes ?? 0;
        const billableIdle = Math.max(0, session.idleMinutes - grace);
        total += proportionalCost(billableIdle, component.stepSize, component.priceMinorUnits);
        break;
      }
    }
  }

  return Math.round(total);
}

function proportionalCost(quantity: number, stepSize: number, priceMinorUnits: number): number {
  if (stepSize <= 0) {
    throw new Error('step_size must be > 0');
  }
  return (quantity / stepSize) * priceMinorUnits;
}

export function hasEnergyOrTimeComponent(components: TariffComponentForm[]): boolean {
  return components.some((c) => c.type === 'energy' || c.type === 'time');
}

export function allStepSizesValid(components: TariffComponentForm[]): boolean {
  return components.every((c) => c.stepSize > 0);
}
