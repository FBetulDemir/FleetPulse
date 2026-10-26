import { NavigationStatus } from '../live/live-events';
import { VesselLiveState } from '../live/fleet-live-store';

/** Telemetry older than this is shown as stale even if the device is still connected. */
export const STALE_AFTER_MS = 10_000;
export const LOW_BATTERY_PERCENT = 20;

/**
 * - live: connected and reporting
 * - stale: connected but silent for too long
 * - offline: the broker reported the device disconnected
 * - waiting: connected, but no telemetry received yet
 */
export type Freshness = 'live' | 'stale' | 'offline' | 'waiting';

export interface VesselRow {
  vesselId: string;
  freshness: Freshness;
  status: NavigationStatus | null;
  speedKnots: number | null;
  courseDegrees: number | null;
  batteryPercent: number | null;
  lowBattery: boolean;
  motorTemperatureC: number | null;
  updatedAt: string | null;
  ageSeconds: number | null;
}

export function toRow(vessel: VesselLiveState, nowMs: number): VesselRow {
  const telemetry = vessel.telemetry;
  const ageMs = telemetry ? Math.max(0, nowMs - Date.parse(telemetry.timestamp)) : null;
  return {
    vesselId: vessel.vesselId,
    freshness: freshness(vessel, ageMs),
    status: telemetry?.status ?? null,
    speedKnots: telemetry?.speed_knots ?? null,
    courseDegrees: telemetry?.course_degrees ?? null,
    batteryPercent: telemetry?.battery_percent ?? null,
    lowBattery: telemetry !== null && telemetry.battery_percent < LOW_BATTERY_PERCENT,
    motorTemperatureC: telemetry?.motor_temperature_c ?? null,
    updatedAt: telemetry?.timestamp ?? null,
    ageSeconds: ageMs === null ? null : Math.floor(ageMs / 1000),
  };
}

function freshness(vessel: VesselLiveState, ageMs: number | null): Freshness {
  if (vessel.connection === 'offline') return 'offline';
  if (ageMs === null) return 'waiting';
  return ageMs > STALE_AFTER_MS ? 'stale' : 'live';
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}
