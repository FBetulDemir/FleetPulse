import { LiveEvent, Telemetry } from '../app/live/live-events';

export function telemetry(overrides: Partial<Telemetry> = {}): Telemetry {
  return {
    schema_version: 1,
    vessel_id: 'vessel-001',
    device_id: 'device-001',
    timestamp: '2026-10-26T10:00:00Z',
    latitude: 57.7089,
    longitude: 11.9746,
    speed_knots: 8.2,
    course_degrees: 142.5,
    battery_percent: 76,
    battery_voltage: 25.0,
    motor_temperature_c: 47.3,
    ambient_temperature_c: 12.5,
    status: 'underway',
    ...overrides,
  };
}

export function telemetryEvent(overrides: Partial<Telemetry> = {}): LiveEvent {
  const data = telemetry(overrides);
  return { type: 'telemetry', vessel_id: data.vessel_id, data };
}
