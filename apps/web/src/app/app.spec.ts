import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { user } from '../testing/users';
import { User } from './api/models';
import { App } from './app';
import { AlertsFeed } from './alerts/alerts-feed';
import { AuthService } from './auth/auth.service';
import { LiveConnection, SocketState } from './live/live-connection';

describe('App', () => {
  const state = signal<SocketState>('connecting');
  const currentUser = signal<User | null>(null);
  const auth = { user: currentUser, logout: vi.fn() };
  const openAlerts = signal(0);

  beforeEach(() => {
    currentUser.set(null);
    openAlerts.set(0);
    auth.logout.mockReset().mockResolvedValue(undefined);
  });

  async function render(): Promise<HTMLElement> {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        { provide: LiveConnection, useValue: { state } },
        { provide: AuthService, useValue: auth },
        { provide: AlertsFeed, useValue: { openCount: openAlerts } },
      ],
    });
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('labels the data as simulated, even before login', async () => {
    const page = await render();

    expect(page.textContent).toContain('Simulated data');
    expect(page.textContent).not.toContain('Sign out');
  });

  it('shows the logged-in user and the live connection state', async () => {
    currentUser.set(user({ display_name: 'Demo Operator', role: 'operator' }));
    state.set('reconnecting');
    const page = await render();

    expect(page.textContent).toContain('Demo Operator');
    expect(page.querySelector('.socket[role="status"]')?.textContent).toContain('Reconnecting');
  });

  it('signs out', async () => {
    currentUser.set(user());
    const page = await render();

    const signOut = [...page.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Sign out'),
    );
    signOut?.click();

    expect(auth.logout).toHaveBeenCalled();
  });

  it('shows the number of open alerts in the navigation', async () => {
    currentUser.set(user());
    openAlerts.set(3);
    const page = await render();

    const alertsLink = [...page.querySelectorAll('nav a')].find((a) =>
      a.textContent?.includes('Alerts'),
    );
    expect(alertsLink?.textContent?.replace(/\s+/g, ' ').trim()).toBe('Alerts 3 open');
  });
});
