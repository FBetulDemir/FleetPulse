import { VesselRow } from '../app/fleet/vessel-row';

export function row(overrides: Partial<VesselRow> = {}): VesselRow {
  return {
    vesselId: 'vessel-001',
    id: '7f8f6a5e-2a7d-4d43-9c55-8a1f2f0f0001',
    name: 'Älvskutt',
    vesselType: 'ferry',
    freshness: 'live',
    status: 'underway',
    latitude: 57.7,
    longitude: 11.95,
    speedKnots: 8.2,
    courseDegrees: 142,
    batteryPercent: 76,
    lowBattery: false,
    motorTemperatureC: 47.3,
    updatedAt: '2026-10-26T10:00:00Z',
    ageSeconds: 1,
    ...overrides,
  };
}
