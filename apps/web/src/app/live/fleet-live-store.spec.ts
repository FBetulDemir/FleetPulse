import { telemetry, telemetryEvent } from '../../testing/telemetry';
import { applyEvent } from './fleet-live-store';

describe('applyEvent', () => {
  it('adds a vessel on its first telemetry without guessing its connection state', () => {
    const state = applyEvent(new Map(), telemetryEvent());

    expect(state.get('vessel-001')).toEqual({
      vesselId: 'vessel-001',
      connection: null,
      telemetry: telemetry(),
    });
  });

  it('keeps the connection state when new telemetry arrives', () => {
    let state = applyEvent(new Map(), {
      type: 'vessel_status',
      vessel_id: 'vessel-001',
      state: 'offline',
    });

    // A new subscriber receives the last telemetry of an offline vessel; it stays offline.
    state = applyEvent(state, telemetryEvent());

    expect(state.get('vessel-001')?.connection).toBe('offline');
  });

  it('replaces telemetry with the newest reading', () => {
    let state = applyEvent(new Map(), telemetryEvent({ speed_knots: 1 }));
    state = applyEvent(state, telemetryEvent({ speed_knots: 2 }));

    expect(state.get('vessel-001')?.telemetry?.speed_knots).toBe(2);
  });

  it('does not mutate the previous state', () => {
    const before = new Map();

    applyEvent(before, telemetryEvent());

    expect(before.size).toBe(0);
  });
});
