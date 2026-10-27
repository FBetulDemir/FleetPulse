/**
 * Messages exchanged with the API over `/ws`.
 * These mirror the backend contracts in `packages/contracts` and `fleetpulse_backend.api`.
 */

export type NavigationStatus = 'docked' | 'underway' | 'anchored';
export type ConnectionState = 'online' | 'offline';

export interface Telemetry {
  schema_version: 1;
  vessel_id: string;
  device_id: string;
  /** ISO 8601, UTC */
  timestamp: string;
  latitude: number;
  longitude: number;
  speed_knots: number;
  course_degrees: number;
  battery_percent: number;
  battery_voltage: number;
  motor_temperature_c: number;
  ambient_temperature_c: number;
  status: NavigationStatus;
}

export type AlertSeverity = 'info' | 'warning' | 'critical';

/** An alert as sent over the WebSocket (`vessel_id` is the MQTT identifier). */
export interface LiveAlert {
  id: string;
  vessel_id: string;
  alert_type: 'threshold' | 'offline' | 'invalid_telemetry';
  severity: AlertSeverity;
  status: 'active' | 'acknowledged' | 'resolved';
  message: string;
  value: number | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export type LiveEvent =
  | { type: 'telemetry'; vessel_id: string; data: Telemetry }
  | { type: 'vessel_status'; vessel_id: string; state: ConnectionState }
  | {
      type: 'alert';
      vessel_id: string;
      event: 'created' | 'acknowledged' | 'resolved';
      alert: LiveAlert;
    };

export type ControlMessage =
  { type: 'subscribed' | 'unsubscribed'; channel: string } | { type: 'error'; message: string };

export type ServerMessage = LiveEvent | ControlMessage;

export type LiveChannel =
  { channel: 'fleet' } | { channel: 'alerts' } | { channel: 'vessel'; vessel_id: string };

export type ClientMessage = { type: 'subscribe' | 'unsubscribe' } & LiveChannel;

export function isLiveEvent(message: ServerMessage): message is LiveEvent {
  return (
    message.type === 'telemetry' || message.type === 'vessel_status' || message.type === 'alert'
  );
}
