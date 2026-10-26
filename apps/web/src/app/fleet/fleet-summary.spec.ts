import { row } from '../../testing/rows';
import { summarizeFleet } from './fleet-summary';

describe('summarizeFleet', () => {
  it('counts live, not-live and underway vessels and averages the battery', () => {
    const summary = summarizeFleet([
      row({ vesselId: 'a', batteryPercent: 80 }),
      row({ vesselId: 'b', status: 'docked', batteryPercent: 60 }),
      row({ vesselId: 'c', freshness: 'offline', batteryPercent: 10, lowBattery: true }),
      row({ vesselId: 'd', freshness: 'waiting', batteryPercent: null }),
    ]);

    expect(summary).toEqual({
      total: 4,
      live: 2,
      notLive: 2,
      underway: 1,
      averageBattery: 50,
      lowBattery: 1,
    });
  });

  it('has no average battery before any vessel reports one', () => {
    expect(summarizeFleet([row({ batteryPercent: null })]).averageBattery).toBeNull();
  });
});
