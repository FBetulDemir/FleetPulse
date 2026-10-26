import { Signal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { EMPTY, switchMap } from 'rxjs';

import { LiveConnection } from '../live/live-connection';
import { ConnectionState, Telemetry } from '../live/live-events';

/** How much live history the detail page keeps for its charts. */
export const LIVE_WINDOW_MS = 5 * 60_000;

/**
 * Adds a reading and drops readings older than the window. Out-of-order or repeated
 * readings (possible after a reconnect, when the server resends the latest) are ignored.
 */
export function appendReading(
  readings: readonly Telemetry[],
  reading: Telemetry,
  windowMs = LIVE_WINDOW_MS,
): Telemetry[] {
  const time = Date.parse(reading.timestamp);
  const last = readings.at(-1);
  if (last && time <= Date.parse(last.timestamp)) return [...readings];
  return [...readings, reading].filter((r) => Date.parse(r.timestamp) > time - windowMs);
}

export interface LiveFeed {
  readings: Signal<Telemetry[]>;
  latest: Signal<Telemetry | null>;
  connection: Signal<ConnectionState | null>;
}

/**
 * Live readings for one vessel. Call in an injection context (e.g. a component field);
 * it follows `vesselId` and stops when the component is destroyed.
 */
export function liveFeed(vesselId: Signal<string | undefined>): LiveFeed {
  const live = inject(LiveConnection);
  const readings = signal<Telemetry[]>([]);
  const connection = signal<ConnectionState | null>(null);

  toObservable(vesselId)
    .pipe(
      switchMap((id) => {
        readings.set([]);
        connection.set(null);
        return id ? live.watch({ channel: 'vessel', vessel_id: id }) : EMPTY;
      }),
      takeUntilDestroyed(),
    )
    .subscribe((event) => {
      if (event.type === 'telemetry') readings.update((r) => appendReading(r, event.data));
      else connection.set(event.state);
    });

  return {
    readings: readings.asReadonly(),
    latest: computed(() => readings().at(-1) ?? null),
    connection: connection.asReadonly(),
  };
}
