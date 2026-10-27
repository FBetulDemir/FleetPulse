import { httpResource } from '@angular/common/http';
import { Service, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { EMPTY, distinctUntilChanged, map, switchMap } from 'rxjs';

import { AlertPage, VesselPage } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveConnection } from '../live/live-connection';
import { LiveAlert, LiveEvent } from '../live/live-events';

export const OPEN_ALERTS_URL = '/api/v1/alerts';
export const VESSEL_NAMES_URL = '/api/v1/vessels';

const SEVERITY_LABELS = { info: 'Info', warning: 'Warning', critical: 'Critical' } as const;

/**
 * Alerts while someone is signed in: the number of open alerts, a notification when a
 * new one arrives, and a change counter that pages watch to refresh their lists.
 */
@Service()
export class AlertsFeed {
  private readonly auth = inject(AuthService);
  private readonly live = inject(LiveConnection);
  private readonly snackBar = inject(MatSnackBar);
  private readonly router = inject(Router);

  private readonly changesSignal = signal(0);
  /** Increases with every alert event (created, acknowledged or resolved). */
  readonly changes = this.changesSignal.asReadonly();

  private readonly openAlerts = httpResource<AlertPage>(() =>
    this.auth.user() ? { url: OPEN_ALERTS_URL, params: { status: 'open', limit: 1 } } : undefined,
  );
  readonly openCount = computed(() =>
    this.openAlerts.hasValue() ? this.openAlerts.value().total : 0,
  );

  private readonly vessels = httpResource<VesselPage>(() =>
    this.auth.user() ? { url: VESSEL_NAMES_URL, params: { limit: 100 } } : undefined,
  );
  private readonly vesselNames = computed(
    () =>
      new Map(
        this.vessels.hasValue()
          ? this.vessels.value().items.map((v) => [v.identifier, v.name] as const)
          : [],
      ),
  );

  constructor() {
    // Listen only while signed in; signing out ends the subscription.
    toObservable(this.auth.user)
      .pipe(
        map((user) => user !== null),
        distinctUntilChanged(),
        switchMap((signedIn) => (signedIn ? this.live.watch({ channel: 'alerts' }) : EMPTY)),
        takeUntilDestroyed(),
      )
      .subscribe((event) => this.onEvent(event));
  }

  private onEvent(event: LiveEvent): void {
    if (event.type !== 'alert') return;
    this.changesSignal.update((n) => n + 1);
    this.openAlerts.reload();
    if (event.event === 'created' && event.alert.severity !== 'info') this.notify(event.alert);
  }

  private notify(alert: LiveAlert): void {
    const vessel = this.vesselNames().get(alert.vessel_id) ?? alert.vessel_id;
    const message = `${SEVERITY_LABELS[alert.severity]} · ${vessel}: ${alert.message}`;
    this.snackBar
      .open(message, 'View alerts', {
        duration: 8000,
        // Critical alerts interrupt the screen reader; others wait their turn.
        politeness: alert.severity === 'critical' ? 'assertive' : 'polite',
        panelClass: `fp-snack-${alert.severity}`,
      })
      .onAction()
      .subscribe(() => void this.router.navigateByUrl('/alerts'));
  }
}
