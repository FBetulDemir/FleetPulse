import { telemetry } from '../../testing/telemetry';
import { registeredVessel } from '../../testing/vessels';
import { VesselLiveState } from '../live/fleet-live-store';
import { STALE_AFTER_MS, buildRows, formatAge, toRow } from './vessel-row';

const READING_AT = Date.parse('2026-10-26T10:00:00Z');

function live(overrides: Partial<VesselLiveState> = {}): VesselLiveState {
  return { vesselId: 'vessel-001', connection: 'online', telemetry: telemetry(), ...overrides };
}

describe('toRow', () => {
  const registered = registeredVessel();

  it('combines registry details with live readings', () => {
    const row = toRow('vessel-001', registered, live(), READING_AT + 2000);

    expect(row).toMatchObject({
      vesselId: 'vessel-001',
      name: 'Älvskutt',
      vesselType: 'ferry',
      freshness: 'live',
      ageSeconds: 2,
      speedKnots: 8.2,
    });
  });

  it('falls back to the identifier for unregistered vessels', () => {
    const row = toRow('vessel-009', undefined, live({ vesselId: 'vessel-009' }), READING_AT);

    expect(row.name).toBe('vessel-009');
    expect(row.vesselType).toBeNull();
  });

  it('is stale when a connected device stops reporting', () => {
    const row = toRow('vessel-001', registered, live(), READING_AT + STALE_AFTER_MS + 1);

    expect(row.freshness).toBe('stale');
  });

  it('is offline when the broker reports a disconnect, even with recent telemetry', () => {
    const row = toRow('vessel-001', registered, live({ connection: 'offline' }), READING_AT);

    expect(row.freshness).toBe('offline');
  });

  it('is waiting for a registered vessel that has not reported yet', () => {
    const row = toRow('vessel-001', registered, undefined, READING_AT);

    expect(row.freshness).toBe('waiting');
    expect(row.batteryPercent).toBeNull();
    expect(row.lowBattery).toBe(false);
  });

  it('flags low battery below 20 percent', () => {
    const lowBattery = (percent: number) =>
      toRow(
        'vessel-001',
        registered,
        live({ telemetry: telemetry({ battery_percent: percent }) }),
        READING_AT,
      ).lowBattery;

    expect(lowBattery(19.9)).toBe(true);
    expect(lowBattery(20)).toBe(false);
  });
});

describe('buildRows', () => {
  it('includes registered and reporting vessels, sorted by name', () => {
    const rows = buildRows(
      [
        registeredVessel({ identifier: 'vessel-002', name: 'Bravo' }),
        registeredVessel({ identifier: 'vessel-001', name: 'alpha' }),
      ],
      [live({ vesselId: 'vessel-001' }), live({ vesselId: 'vessel-003' })],
      READING_AT,
    );

    expect(rows.map((row) => [row.name, row.freshness])).toEqual([
      ['alpha', 'live'],
      ['Bravo', 'waiting'],
      ['vessel-003', 'live'],
    ]);
  });
});

describe('formatAge', () => {
  it.each([
    [null, '—'],
    [0, 'just now'],
    [12, '12 s ago'],
    [125, '2 min ago'],
    [7200, '2 h ago'],
  ])('formats %s seconds as "%s"', (seconds, expected) => {
    expect(formatAge(seconds)).toBe(expected);
  });
});
