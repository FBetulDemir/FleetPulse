import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { user } from '../../testing/users';
import { Alert, AlertPage as AlertPageData, Role, User } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { AlertsFeed } from './alerts-feed';
import { ALERTS_URL, AlertsPage } from './alerts-page';

function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 'a1',
    vessel_id: 'v1',
    vessel_identifier: 'vessel-003',
    vessel_name: 'Vinga Pilot',
    alert_type: 'threshold',
    severity: 'critical',
    status: 'active',
    message: 'High motor temperature: 71.0 °C (above 70 °C)',
    value: 71,
    triggered_at: new Date(Date.now() - 120_000).toISOString(),
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    ...overrides,
  };
}

const page = (items: Alert[]): AlertPageData => ({
  items,
  total: items.length,
  limit: 100,
  offset: 0,
});

describe('AlertsPage', () => {
  const currentUser = signal<User | null>(null);
  const changes = signal(0);
  let fixture: ComponentFixture<AlertsPage>;
  let http: HttpTestingController;

  async function render(role: Role, alerts: Alert[]) {
    currentUser.set(user({ role }));
    TestBed.configureTestingModule({
      imports: [AlertsPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { user: currentUser } },
        { provide: AlertsFeed, useValue: { changes } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AlertsPage);
    TestBed.tick();
    // Exactly one request on load (a toggle-group quirk used to cause a second one).
    http.expectOne((r) => r.url === ALERTS_URL).flush(page(alerts));
    await fixture.whenStable();
  }

  afterEach(() => http.verify());

  const host = () => fixture.nativeElement as HTMLElement;
  const acknowledgeButton = () =>
    [...host().querySelectorAll('button')].find((b) => b.textContent?.includes('Acknowledge'));

  it('lists open alerts with severity, vessel and age', async () => {
    await render('viewer', [alert()]);

    const item = host().querySelector('.alert')?.textContent?.replace(/\s+/g, ' ');
    expect(item).toContain('Critical');
    expect(item).toContain('High motor temperature');
    expect(item).toContain('Vinga Pilot');
    expect(item).toContain('2 min ago');
    expect(item).toContain('Active');
  });

  it('only lets operators and admins acknowledge', async () => {
    await render('viewer', [alert()]);

    expect(acknowledgeButton()).toBeUndefined();
  });

  it('acknowledges an alert and reloads the list', async () => {
    await render('operator', [alert()]);

    acknowledgeButton()!.click();
    http.expectOne(`${ALERTS_URL}/a1/acknowledge`).flush(alert({ status: 'acknowledged' }));
    await new Promise((resolve) => setTimeout(resolve));
    TestBed.tick();
    http
      .expectOne((r) => r.url === ALERTS_URL)
      .flush(page([alert({ status: 'acknowledged', acknowledged_by: 'Demo Operator' })]));
    await fixture.whenStable();

    expect(host().textContent).toContain('Acknowledged by Demo Operator');
    expect(acknowledgeButton()).toBeUndefined();
  });

  it('filters by status and reloads when an alert changes elsewhere', async () => {
    await render('viewer', []);
    expect(host().textContent).toContain('No open alerts');

    changes.update((n) => n + 1);
    TestBed.tick();
    const reload = http.expectOne((r) => r.url === ALERTS_URL);
    expect(reload.request.params.get('status')).toBe('open');
    reload.flush(page([]));
  });
});
