import { Vessel, VesselType } from '../api/models';
import { VesselLiveState } from '../live/fleet-live-store';
import { ConnectionState, NavigationStatus } from '../live/live-events';

/** Telemetry older than this is shown as stale even if the device is still connected. */
export const STALE_AFTER_MS = 10_000;
export const LOW_BATTERY_PERCENT = 20;

/**
 * - live: connected and reporting
 * - stale: connected but silent for too long
 * - offline: the broker reported the device disconnected
 * - waiting: no telemetry received yet
 */
export type Freshness = 'live' | 'stale' | 'offline' | 'waiting';

/** Shown with an icon and text, never color alone. */
export const FRESHNESS_LABELS: Record<Freshness, { label: string; icon: string }> = {
  live: { label: 'Live', icon: 'sensors' },
  stale: { label: 'Stale', icon: 'history' },
  offline: { label: 'Offline', icon: 'sensors_off' },
  waiting: { label: 'Waiting', icon: 'hourglass_empty' },
};

export interface VesselRow {
  /** The vessel's MQTT identifier, e.g. "vessel-001". */
  vesselId: string;
  /** The registry id, used in links; null for vessels that are not registered. */
  id: string | null;
  /** From the vessel registry; falls back to the identifier for unregistered vessels. */
  name: string;
  vesselType: VesselType | null;
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

/**
 * Joins registered vessels (from the API) with live state (from the WebSocket).
 *
 * Vessels appear if they are registered or reporting, so the table still works when
 * the registry fails to load, and new devices show up before they are registered.
 */
export function buildRows(
  registered: readonly Vessel[],
  live: readonly VesselLiveState[],
  nowMs: number,
): VesselRow[] {
  const registry = new Map(registered.map((vessel) => [vessel.identifier, vessel]));
  const liveById = new Map(live.map((state) => [state.vesselId, state]));
  const ids = new Set([...registry.keys(), ...liveById.keys()]);
  return [...ids]
    .map((id) => toRow(id, registry.get(id), liveById.get(id), nowMs))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
}

export function toRow(
  vesselId: string,
  vessel: Vessel | undefined,
  live: VesselLiveState | undefined,
  nowMs: number,
): VesselRow {
  const telemetry = live?.telemetry ?? null;
  const ageMs = telemetry ? Math.max(0, nowMs - Date.parse(telemetry.timestamp)) : null;
  return {
    vesselId,
    id: vessel?.id ?? null,
    name: vessel?.name ?? vesselId,
    vesselType: vessel?.vessel_type ?? null,
    freshness: freshness(live?.connection ?? null, ageMs),
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

function freshness(connection: ConnectionState | null, ageMs: number | null): Freshness {
  if (connection === 'offline') return 'offline';
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
