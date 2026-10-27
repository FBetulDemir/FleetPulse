import { HttpClient, httpResource } from '@angular/common/http';
import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { firstValueFrom, interval, map } from 'rxjs';

import { Alert, AlertPage } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { formatAge } from '../fleet/vessel-row';
import { AlertSeverity } from '../live/live-events';
import { AlertsFeed } from './alerts-feed';

export const ALERTS_URL = '/api/v1/alerts';

type StatusFilter = 'open' | 'all' | 'resolved';
type SeverityFilter = 'all' | AlertSeverity;

export const SEVERITY_DISPLAY: Record<AlertSeverity, { label: string; icon: string }> = {
  critical: { label: 'Critical', icon: 'error' },
  warning: { label: 'Warning', icon: 'warning' },
  info: { label: 'Info', icon: 'info' },
};

@Component({
  selector: 'app-alerts-page',
  imports: [
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressBarModule,
    MatSelectModule,
    RouterLink,
  ],
  templateUrl: './alerts-page.html',
  styleUrl: './alerts-page.scss',
})
export class AlertsPage {
  private readonly http = inject(HttpClient);
  private readonly snackBar = inject(MatSnackBar);
  private readonly feed = inject(AlertsFeed);
  private readonly auth = inject(AuthService);

  protected readonly status = signal<StatusFilter>('open');
  protected readonly severity = signal<SeverityFilter>('all');

  protected readonly alerts = httpResource<AlertPage>(() => {
    const params: Record<string, string> = { limit: '100' };
    if (this.status() !== 'all') params['status'] = this.status();
    if (this.severity() !== 'all') params['severity'] = this.severity();
    return { url: ALERTS_URL, params };
  });

  protected readonly canAcknowledge = computed(() => {
    const role = this.auth.user()?.role;
    return role === 'operator' || role === 'admin';
  });
  protected readonly acknowledging = signal<ReadonlySet<string>>(new Set());

  /** Keeps "x min ago" current. */
  private readonly now = toSignal(interval(15_000).pipe(map(() => Date.now())), {
    initialValue: Date.now(),
  });

  protected readonly severities = SEVERITY_DISPLAY;

  constructor() {
    // Refresh the list whenever an alert is created, acknowledged or resolved.
    let initial = true;
    effect(() => {
      this.feed.changes();
      if (initial) {
        initial = false;
        return;
      }
      untracked(() => this.alerts.reload());
    });
  }

  /**
   * Material's toggle group emits `undefined` and then the bound value while it starts
   * up. Passing that on would flip the filter and back, and load the list twice.
   */
  protected setStatus(value: StatusFilter | undefined): void {
    if (value) this.status.set(value);
  }

  protected age(iso: string): string {
    return formatAge(Math.max(0, Math.floor((this.now() - Date.parse(iso)) / 1000)));
  }

  protected formatTime(iso: string): string {
    return new Date(iso).toLocaleString();
  }

  protected async acknowledge(alert: Alert): Promise<void> {
    this.acknowledging.update((ids) => new Set(ids).add(alert.id));
    try {
      await firstValueFrom(this.http.post(`${ALERTS_URL}/${alert.id}/acknowledge`, null));
      this.alerts.reload();
    } catch {
      this.snackBar.open('The alert could not be acknowledged. Please try again.', 'Close', {
        duration: 6000,
      });
    } finally {
      this.acknowledging.update((ids) => {
        const next = new Set(ids);
        next.delete(alert.id);
        return next;
      });
    }
  }
}
