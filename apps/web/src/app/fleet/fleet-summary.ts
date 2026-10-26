import { VesselRow } from './vessel-row';

export interface FleetSummary {
  total: number;
  live: number;
  /** Offline, stale or not reporting yet: the vessels that need a look. */
  notLive: number;
  underway: number;
  /** Average over vessels that have reported a battery level; null if none have. */
  averageBattery: number | null;
  lowBattery: number;
}

export function summarizeFleet(rows: readonly VesselRow[]): FleetSummary {
  const batteries = rows
    .map((row) => row.batteryPercent)
    .filter((value): value is number => value !== null);
  const live = rows.filter((row) => row.freshness === 'live').length;
  return {
    total: rows.length,
    live,
    notLive: rows.length - live,
    underway: rows.filter((row) => row.freshness === 'live' && row.status === 'underway').length,
    averageBattery: batteries.length
      ? batteries.reduce((sum, value) => sum + value, 0) / batteries.length
      : null,
    lowBattery: rows.filter((row) => row.lowBattery).length,
  };
}
