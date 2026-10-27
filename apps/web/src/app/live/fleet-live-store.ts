import { Service, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { LiveConnection } from './live-connection';
import { ConnectionState, LiveEvent, Telemetry } from './live-events';

export interface VesselLiveState {
  vesselId: string;
  /** Null until the broker has reported the device's connection state. */
  connection: ConnectionState | null;
  telemetry: Telemetry | null;
}

type FleetState = ReadonlyMap<string, VesselLiveState>;

export function applyEvent(state: FleetState, event: LiveEvent): FleetState {
  if (event.type === 'alert') return state; // alerts have their own feed
  const current = state.get(event.vessel_id) ?? {
    vesselId: event.vessel_id,
    connection: null,
    telemetry: null,
  };
  // Connection state comes only from status messages. Telemetry must not imply "online":
  // a newly subscribed client receives the last telemetry of an offline vessel too.
  const next: VesselLiveState =
    event.type === 'telemetry'
      ? { ...current, telemetry: event.data }
      : { ...current, connection: event.state };
  return new Map(state).set(event.vessel_id, next);
}

/** Latest known state of every vessel, kept up to date from the live fleet channel. */
@Service()
export class FleetLiveStore {
  private readonly connection = inject(LiveConnection);
  private readonly state = signal<FleetState>(new Map());

  readonly socketState = this.connection.state;
  readonly vessels = computed(() =>
    [...this.state().values()].sort((a, b) => a.vesselId.localeCompare(b.vesselId)),
  );

  constructor() {
    this.connection
      .watch({ channel: 'fleet' })
      .pipe(takeUntilDestroyed())
      .subscribe((event) => this.state.update((state) => applyEvent(state, event)));
  }
}
