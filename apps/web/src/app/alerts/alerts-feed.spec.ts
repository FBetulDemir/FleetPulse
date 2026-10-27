import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';

import { registeredVessel, vesselPage } from '../../testing/vessels';
import { user } from '../../testing/users';
import { User } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveConnection } from '../live/live-connection';
import { LiveAlert, LiveChannel, LiveEvent } from '../live/live-events';
import { AlertsFeed, OPEN_ALERTS_URL, VESSEL_NAMES_URL } from './alerts-feed';

function alertEvent(
  event: 'created' | 'acknowledged' | 'resolved',
  overrides: Partial<LiveAlert> = {},
): LiveEvent {
  const alert: LiveAlert = {
    id: 'a1',
    vessel_id: 'vessel-003',
    alert_type: 'threshold',
    severity: 'critical',
    status: 'active',
    message: 'High motor temperature: 71.0 °C (above 70 °C)',
    value: 71,
    triggered_at: '2026-10-27T10:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    ...overrides,
  };
  return { type: 'alert', vessel_id: alert.vessel_id, event, alert };
}

describe('AlertsFeed', () => {
  const currentUser = signal<User | null>(null);
  const events = new Subject<LiveEvent>();
  const watched: LiveChannel[] = [];
  const snackBar = { open: vi.fn() };
  let feed: AlertsFeed;
  let http: HttpTestingController;

  beforeEach(() => {
    currentUser.set(null);
    watched.length = 0;
    snackBar.open.mockReset().mockReturnValue({ onAction: () => of() });
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { user: currentUser } },
        {
          provide: LiveConnection,
          useValue: {
            watch: (channel: LiveChannel) => {
              watched.push(channel);
              return events;
            },
          },
        },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    });
    feed = TestBed.inject(AlertsFeed);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Resources update their value in a microtask after a response. */
  const settle = () => new Promise((resolve) => setTimeout(resolve));

  async function signIn(openAlerts: number): Promise<void> {
    currentUser.set(user());
    TestBed.tick();
    http
      .expectOne((r) => r.url === OPEN_ALERTS_URL)
      .flush({ items: [], total: openAlerts, limit: 1, offset: 0 });
    http
      .expectOne((r) => r.url === VESSEL_NAMES_URL)
      .flush(vesselPage([registeredVessel({ identifier: 'vessel-003', name: 'Vinga Pilot' })]));
    await settle();
  }

  it('does nothing until someone signs in', () => {
    TestBed.tick();

    expect(watched).toEqual([]);
    http.expectNone(() => true);
  });

  it('listens only to the alerts channel and counts open alerts', async () => {
    await signIn(2);

    expect(watched).toEqual([{ channel: 'alerts' }]);
    expect(feed.openCount()).toBe(2);
  });

  it('notifies about new alerts by vessel name and refreshes the count', async () => {
    await signIn(0);

    events.next(alertEvent('created'));

    expect(snackBar.open).toHaveBeenCalledWith(
      'Critical · Vinga Pilot: High motor temperature: 71.0 °C (above 70 °C)',
      'View alerts',
      expect.objectContaining({ politeness: 'assertive' }),
    );
    expect(feed.changes()).toBe(1);
    TestBed.tick(); // sends the count's reload request
    http
      .expectOne((r) => r.url === OPEN_ALERTS_URL)
      .flush({ items: [], total: 1, limit: 1, offset: 0 });
    await settle();
    expect(feed.openCount()).toBe(1);
  });

  it('does not pop up for resolved alerts or info alerts', async () => {
    await signIn(1);

    events.next(alertEvent('resolved'));
    events.next(alertEvent('created', { severity: 'info' }));

    expect(snackBar.open).not.toHaveBeenCalled();
    expect(feed.changes()).toBe(2);
    TestBed.tick();
    http.match((r) => r.url === OPEN_ALERTS_URL).forEach((r) => r.flush({ items: [], total: 0 }));
  });
});
