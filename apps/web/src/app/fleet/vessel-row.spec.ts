import { telemetry } from '../../testing/telemetry';
import { VesselLiveState } from '../live/fleet-live-store';
import { STALE_AFTER_MS, formatAge, toRow } from './vessel-row';

const READING_AT = Date.parse('2026-10-26T10:00:00Z');

function vessel(overrides: Partial<VesselLiveState> = {}): VesselLiveState {
  return { vesselId: 'vessel-001', connection: 'online', telemetry: telemetry(), ...overrides };
}

describe('toRow', () => {
  it('is live while telemetry is recent', () => {
    const row = toRow(vessel(), READING_AT + 2000);

    expect(row.freshness).toBe('live');
    expect(row.ageSeconds).toBe(2);
    expect(row.speedKnots).toBe(8.2);
  });

  it('is stale when a connected device stops reporting', () => {
    expect(toRow(vessel(), READING_AT + STALE_AFTER_MS + 1).freshness).toBe('stale');
  });

  it('is offline when the broker reports a disconnect, even with recent telemetry', () => {
    expect(toRow(vessel({ connection: 'offline' }), READING_AT).freshness).toBe('offline');
  });

  it('is waiting before the first telemetry arrives', () => {
    const row = toRow(vessel({ telemetry: null }), READING_AT);

    expect(row.freshness).toBe('waiting');
    expect(row.batteryPercent).toBeNull();
    expect(row.lowBattery).toBe(false);
  });

  it('flags low battery below 20 percent', () => {
    expect(
      toRow(vessel({ telemetry: telemetry({ battery_percent: 19.9 }) }), READING_AT).lowBattery,
    ).toBe(true);
    expect(
      toRow(vessel({ telemetry: telemetry({ battery_percent: 20 }) }), READING_AT).lowBattery,
    ).toBe(false);
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
