import { DecimalPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { interval, map } from 'rxjs';

import { FleetLiveStore } from '../live/fleet-live-store';
import { Freshness, VesselRow, formatAge, toRow } from './vessel-row';

const FRESHNESS_LABELS: Record<Freshness, { label: string; icon: string }> = {
  live: { label: 'Live', icon: 'sensors' },
  stale: { label: 'Stale', icon: 'history' },
  offline: { label: 'Offline', icon: 'sensors_off' },
  waiting: { label: 'Waiting', icon: 'hourglass_empty' },
};

@Component({
  selector: 'app-fleet-page',
  imports: [
    DecimalPipe,
    MatIconModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatTableModule,
  ],
  templateUrl: './fleet-page.html',
  styleUrl: './fleet-page.scss',
})
export class FleetPage {
  private readonly store = inject(FleetLiveStore);

  /** Ticks every second so "x s ago" and staleness update without new data. */
  private readonly now = toSignal(interval(1000).pipe(map(() => Date.now())), {
    initialValue: Date.now(),
  });

  protected readonly rows = computed(() =>
    this.store.vessels().map((vessel) => toRow(vessel, this.now())),
  );
  protected readonly columns = [
    'vessel',
    'freshness',
    'status',
    'speed',
    'course',
    'battery',
    'motorTemperature',
    'updated',
  ];
  protected readonly caption = computed(() => `Live status of ${this.rows().length} vessels`);
  protected readonly formatAge = formatAge;

  protected freshnessLabel(freshness: Freshness): string {
    return FRESHNESS_LABELS[freshness].label;
  }

  protected freshnessIcon(freshness: Freshness): string {
    return FRESHNESS_LABELS[freshness].icon;
  }

  protected trackByVessel(_index: number, row: VesselRow): string {
    return row.vesselId;
  }
}
