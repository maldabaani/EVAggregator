export type TariffComponentType = 'energy' | 'time' | 'flat' | 'idle';

export interface TariffComponentForm {
  type: TariffComponentType;
  priceMinorUnits: number;
  stepSize: number;
  appliesAfterMinutes: number | null;
}

export interface SampleSession {
  durationMinutes: number;
  kwh: number;
  idleMinutes: number;
}
