import { DecimalPipe } from '@angular/common';
import { httpResource } from '@angular/common/http';
import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { interval, map } from 'rxjs';

import { VesselPage } from '../api/models';
import { FleetLiveStore } from '../live/fleet-live-store';
import { Freshness, VesselRow, buildRows, formatAge } from './vessel-row';

export const VESSELS_URL = '/api/v1/vessels?is_active=true&limit=100';

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
    MatButtonModule,
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

  /** Registered vessels: names and types. Live readings come from the store. */
  protected readonly registry = httpResource<VesselPage>(() => VESSELS_URL);

  /** Ticks every second so "x s ago" and staleness update without new data. */
  private readonly now = toSignal(interval(1000).pipe(map(() => Date.now())), {
    initialValue: Date.now(),
  });

  protected readonly rows = computed(() =>
    // value() throws while the resource is in an error state, so check hasValue() first.
    buildRows(
      this.registry.hasValue() ? this.registry.value().items : [],
      this.store.vessels(),
      this.now(),
    ),
  );
  protected readonly columns = [
    'vessel',
    'type',
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
