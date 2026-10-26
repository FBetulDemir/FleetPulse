import { Telemetry } from '../live/live-events';

/** Metrics the history API accepts (course is excluded: angles cannot be averaged). */
export type HistoryMetric =
  | 'speed_knots'
  | 'battery_percent'
  | 'battery_voltage'
  | 'motor_temperature_c'
  | 'ambient_temperature_c';

export interface MetricInfo {
  label: string;
  unit: string;
  /** Digits after the decimal point when displayed. */
  decimals: number;
}

export const METRICS: Record<HistoryMetric, MetricInfo> = {
  speed_knots: { label: 'Speed', unit: 'kn', decimals: 1 },
  battery_percent: { label: 'Battery', unit: '%', decimals: 0 },
  battery_voltage: { label: 'Battery voltage', unit: 'V', decimals: 2 },
  motor_temperature_c: { label: 'Motor temperature', unit: '°C', decimals: 1 },
  ambient_temperature_c: { label: 'Ambient temperature', unit: '°C', decimals: 1 },
};

export const HISTORY_METRICS = Object.keys(METRICS) as HistoryMetric[];

export function formatValue(value: number | null | undefined, metric: MetricInfo): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(metric.decimals)} ${metric.unit}`;
}

export function metricValue(telemetry: Telemetry, metric: HistoryMetric): number {
  return telemetry[metric];
}
