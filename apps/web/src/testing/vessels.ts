import { Vessel, VesselPage } from '../app/api/models';

export function registeredVessel(overrides: Partial<Vessel> = {}): Vessel {
  return {
    id: '7f8f6a5e-2a7d-4d43-9c55-8a1f2f0f0001',
    identifier: 'vessel-001',
    name: 'Älvskutt',
    vessel_type: 'ferry',
    length_m: 24,
    is_active: true,
    created_at: '2026-10-26T09:00:00Z',
    updated_at: '2026-10-26T09:00:00Z',
    ...overrides,
  };
}

export function vesselPage(items: Vessel[]): VesselPage {
  return { items, total: items.length, limit: 100, offset: 0 };
}
