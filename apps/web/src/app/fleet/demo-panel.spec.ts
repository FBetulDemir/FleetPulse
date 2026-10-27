import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';

import { user } from '../../testing/users';
import { registeredVessel } from '../../testing/vessels';
import { Role, User } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { AUTH_OPTIONS_URL } from '../auth/login-page';
import { DemoPanel, SCENARIOS_URL } from './demo-panel';

describe('DemoPanel', () => {
  const currentUser = signal<User | null>(null);
  const snackBar = { open: vi.fn() };
  let fixture: ComponentFixture<DemoPanel>;
  let http: HttpTestingController;

  async function render(role: Role, demoMode = true) {
    currentUser.set(user({ role }));
    snackBar.open.mockReset();
    TestBed.configureTestingModule({
      imports: [DemoPanel],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { user: currentUser } },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(DemoPanel);
    fixture.componentRef.setInput('vessels', [
      registeredVessel({ id: 'v1', name: 'Älvskutt' }),
      registeredVessel({ id: 'v3', name: 'Vinga Pilot' }),
    ]);
    TestBed.tick();
    http.expectOne(AUTH_OPTIONS_URL).flush({ demo_login: demoMode });
    await fixture.whenStable();
  }

  afterEach(() => http.verify());

  const host = () => fixture.nativeElement as HTMLElement;
  const button = (label: string) =>
    [...host().querySelectorAll('button')].find((b) => b.textContent?.includes(label));

  it('is hidden outside demo mode', async () => {
    await render('admin', false);

    expect(host().textContent?.trim()).toBe('');
  });

  it('asks viewers to sign in with a role that may trigger failures', async () => {
    await render('viewer');

    expect(host().textContent).toContain('Sign in as Operator or Admin');
    expect(button('Overheat motor')).toBeUndefined();
  });

  it('starts a scenario on the chosen vessel and says what to expect', async () => {
    await render('operator');

    button('Overheat motor')!.click();
    const request = http.expectOne(SCENARIOS_URL);
    expect(request.request.body).toEqual({ vessel_id: 'v1', scenario: 'overheat' });
    request.flush(
      { vessel_id: 'v1', scenario: 'overheat' },
      { status: 202, statusText: 'Accepted' },
    );
    await fixture.whenStable();

    expect(snackBar.open).toHaveBeenCalledWith(
      'Overheat motor started on Älvskutt. A critical alert appears in about 20 seconds.',
      'OK',
      expect.anything(),
    );
  });

  it('explains the rate limit', async () => {
    await render('admin');

    button('Go offline')!.click();
    http.expectOne(SCENARIOS_URL).flush(null, { status: 429, statusText: 'Too Many Requests' });
    await fixture.whenStable();

    expect(snackBar.open.mock.calls[0][0]).toContain('Try again in a minute');
  });
});
