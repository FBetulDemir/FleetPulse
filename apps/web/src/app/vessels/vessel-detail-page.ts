import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { NgxEchartsDirective } from 'ngx-echarts';
import { interval, map } from 'rxjs';

import { TelemetryHistory, Vessel } from '../api/models';
import {
  RangePoint,
  TimePoint,
  TimeRange,
  rangeOption,
  trendOption,
} from '../charts/chart-options';
import { CHART_THEMES } from '../charts/chart-theme';
import { ColorScheme } from '../charts/color-scheme';
import { Telemetry } from '../live/live-events';
import { FRESHNESS_LABELS, formatAge, toRow } from '../fleet/vessel-row';
import { LIVE_WINDOW_MS, liveFeed } from './live-feed';
import { HISTORY_METRICS, HistoryMetric, METRICS, formatValue } from './metrics';

export const HISTORY_RANGES_HOURS = [1, 6, 24, 72] as const;
type RangeHours = (typeof HISTORY_RANGES_HOURS)[number];

const HISTORY_TAB = 1;

@Component({
  selector: 'app-vessel-detail-page',
  imports: [
    DecimalPipe,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTabsModule,
    NgxEchartsDirective,
    RouterLink,
  ],
  templateUrl: './vessel-detail-page.html',
  styleUrl: './vessel-detail-page.scss',
})
export class VesselDetailPage {
  /** The vessel's registry id, from the route (/vessels/:id). */
  readonly id = input.required<string>();

  private readonly scheme = inject(ColorScheme).scheme;
  private readonly theme = computed(() => CHART_THEMES[this.scheme()]);
  private readonly now = toSignal(interval(1000).pipe(map(() => Date.now())), {
    initialValue: Date.now(),
  });

  protected readonly vessel = httpResource<Vessel>(() => `/api/v1/vessels/${this.id()}`);
  protected readonly notFound = computed(
    () => (this.vessel.error() as HttpErrorResponse | undefined)?.status === 404,
  );
  private readonly identifier = computed(() =>
    this.vessel.hasValue() ? this.vessel.value().identifier : undefined,
  );

  // Live: the last stored reading until the first live one arrives.
  private readonly stored = httpResource<Telemetry>(
    () => `/api/v1/vessels/${this.id()}/telemetry/latest`,
  );
  private readonly feed = liveFeed(this.identifier);
  protected readonly latest = computed(
    () => this.feed.latest() ?? (this.stored.hasValue() ? this.stored.value() : null),
  );
  protected readonly status = computed(() =>
    toRow(
      this.identifier() ?? '',
      this.vessel.hasValue() ? this.vessel.value() : undefined,
      {
        vesselId: this.identifier() ?? '',
        connection: this.feed.connection(),
        telemetry: this.latest(),
      },
      this.now(),
    ),
  );
  protected readonly freshness = computed(() => FRESHNESS_LABELS[this.status().freshness]);
  protected readonly hasLiveTrend = computed(() => this.feed.readings().length >= 2);
  protected readonly speedTrend = computed(() => this.trend('speed_knots'));
  protected readonly motorTrend = computed(() => this.trend('motor_temperature_c'));

  // History: only requested once the History tab has been opened.
  protected readonly metrics = HISTORY_METRICS.map((key) => ({ key, ...METRICS[key] }));
  protected readonly ranges = HISTORY_RANGES_HOURS;
  protected readonly metric = signal<HistoryMetric>('speed_knots');
  protected readonly rangeHours = signal<RangeHours>(1);
  private readonly historyOpened = signal(false);
  private readonly historyRefresh = signal(0);
  protected readonly history = httpResource<TelemetryHistory>(() => {
    if (!this.historyOpened()) return undefined;
    this.historyRefresh(); // re-read so "Refresh" moves the time window to now
    const end = new Date();
    const start = new Date(end.getTime() - this.rangeHours() * 3_600_000);
    return {
      url: `/api/v1/vessels/${this.id()}/telemetry/history`,
      params: { metric: this.metric(), from: start.toISOString(), to: end.toISOString() },
    };
  });
  protected readonly historyInfo = computed(() => METRICS[this.metric()]);
  protected readonly historyPoints = computed<RangePoint[]>(() =>
    this.history.hasValue()
      ? this.history
          .value()
          .buckets.map((b) => [Date.parse(b.time), b.avg, b.min, b.max] satisfies RangePoint)
      : [],
  );
  protected readonly historyChart = computed(() => {
    const info = this.historyInfo();
    const result = this.history.hasValue() ? this.history.value() : null;
    const range: TimeRange = result ? [Date.parse(result.start), Date.parse(result.end)] : [0, 0];
    return rangeOption(
      this.historyPoints(),
      this.theme(),
      {
        description: `${info.label} over the last ${this.rangeHours()} hours: average with min-max range`,
        unit: info.unit,
        decimals: info.decimals,
      },
      range,
    );
  });

  protected readonly formatValue = formatValue;
  protected readonly formatAge = formatAge;
  protected readonly metricInfo = METRICS;

  protected onTabChange(index: number): void {
    if (index === HISTORY_TAB) this.historyOpened.set(true);
  }

  protected refreshHistory(): void {
    this.historyRefresh.update((n) => n + 1);
  }

  protected formatTime(iso: string): string {
    return new Date(iso).toLocaleString();
  }

  private trend(metric: HistoryMetric) {
    const info = METRICS[metric];
    const readings = this.feed.readings();
    const points = readings.map((r) => [Date.parse(r.timestamp), r[metric]] satisfies TimePoint);
    const end = points.at(-1)?.[0] ?? 0;
    return trendOption(
      points,
      this.theme(),
      {
        description: `${info.label} over the last 5 minutes`,
        unit: info.unit,
        decimals: info.decimals,
      },
      [end - LIVE_WINDOW_MS, end],
    );
  }
}
