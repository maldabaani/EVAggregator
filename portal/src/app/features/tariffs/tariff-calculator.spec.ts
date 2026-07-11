import { TariffComponentForm } from '../../core/models/tariff.model';
import { allStepSizesValid, calculateSessionCost, hasEnergyOrTimeComponent } from './tariff-calculator';

describe('calculateSessionCost', () => {
  it('calculates the correct total for a sample session (30 min, 15 kWh)', () => {
    const components: TariffComponentForm[] = [
      { type: 'energy', priceMinorUnits: 150, stepSize: 1, appliesAfterMinutes: null },
      { type: 'time', priceMinorUnits: 10, stepSize: 1, appliesAfterMinutes: null },
      { type: 'flat', priceMinorUnits: 200, stepSize: 1, appliesAfterMinutes: null },
    ];

    const total = calculateSessionCost(components, { durationMinutes: 30, kwh: 15, idleMinutes: 0 });

    expect(total).toBe(15 * 150 + 30 * 10 + 200);
  });

  it('charges zero idle cost within the grace period', () => {
    const components: TariffComponentForm[] = [
      { type: 'idle', priceMinorUnits: 50, stepSize: 1, appliesAfterMinutes: 10 },
    ];

    const total = calculateSessionCost(components, { durationMinutes: 0, kwh: 0, idleMinutes: 8 });

    expect(total).toBe(0);
  });

  it('accrues idle cost correctly after the grace period', () => {
    const components: TariffComponentForm[] = [
      { type: 'idle', priceMinorUnits: 50, stepSize: 1, appliesAfterMinutes: 10 },
    ];

    const total = calculateSessionCost(components, { durationMinutes: 0, kwh: 0, idleMinutes: 25 });

    expect(total).toBe(15 * 50);
  });

  it('throws for a zero step size', () => {
    const components: TariffComponentForm[] = [
      { type: 'energy', priceMinorUnits: 100, stepSize: 0, appliesAfterMinutes: null },
    ];

    expect(() => calculateSessionCost(components, { durationMinutes: 0, kwh: 10, idleMinutes: 0 })).toThrow();
  });
});

describe('hasEnergyOrTimeComponent', () => {
  it('is false for a flat/idle-only component list', () => {
    const components: TariffComponentForm[] = [
      { type: 'flat', priceMinorUnits: 100, stepSize: 1, appliesAfterMinutes: null },
    ];

    expect(hasEnergyOrTimeComponent(components)).toBeFalse();
  });

  it('is true once an energy or time component is present', () => {
    const components: TariffComponentForm[] = [
      { type: 'time', priceMinorUnits: 10, stepSize: 1, appliesAfterMinutes: null },
    ];

    expect(hasEnergyOrTimeComponent(components)).toBeTrue();
  });
});

describe('allStepSizesValid', () => {
  it('is false when any component has a non-positive step size', () => {
    const components: TariffComponentForm[] = [
      { type: 'energy', priceMinorUnits: 100, stepSize: 1, appliesAfterMinutes: null },
      { type: 'time', priceMinorUnits: 10, stepSize: 0, appliesAfterMinutes: null },
    ];

    expect(allStepSizesValid(components)).toBeFalse();
  });
});
