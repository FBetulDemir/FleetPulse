import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';

import { user } from '../../testing/users';
import { AuthService } from './auth.service';
import { AUTH_OPTIONS_URL, LoginPage } from './login-page';

describe('LoginPage', () => {
  let fixture: ComponentFixture<LoginPage>;
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;
  const auth = { login: vi.fn(), demoLogin: vi.fn() };

  async function render(query: Record<string, string> = {}, demoLogin = true) {
    TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: auth },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginPage);
    TestBed.tick();
    http.expectOne(AUTH_OPTIONS_URL).flush({ demo_login: demoLogin });
    await fixture.whenStable();
  }

  beforeEach(() => {
    auth.login.mockReset().mockResolvedValue(user());
    auth.demoLogin.mockReset().mockResolvedValue(user());
  });

  const page = () => fixture.nativeElement as HTMLElement;
  const input = (type: string) => page().querySelector<HTMLInputElement>(`input[type="${type}"]`)!;

  async function type(field: HTMLInputElement, value: string): Promise<void> {
    field.value = value;
    field.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function signIn(): Promise<void> {
    page().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  it('shows validation messages instead of submitting an empty form', async () => {
    await render();

    await signIn();

    expect(auth.login).not.toHaveBeenCalled();
    expect(page().textContent).toContain('Enter your email address');
    expect(page().textContent).toContain('Enter your password');
  });

  it('signs in and returns to the page the user came from', async () => {
    await render({ returnUrl: '/vessels' });

    await type(input('email'), 'demo-operator@example.com');
    await type(input('password'), 'secret');
    await signIn();

    expect(auth.login).toHaveBeenCalledWith('demo-operator@example.com', 'secret');
    expect(navigate).toHaveBeenCalledWith('/vessels');
  });

  it('ignores return URLs that leave the site', async () => {
    await render({ returnUrl: 'https://evil.example' });

    await type(input('email'), 'demo-operator@example.com');
    await type(input('password'), 'secret');
    await signIn();

    expect(navigate).toHaveBeenCalledWith('/');
  });

  it('shows one message for wrong credentials', async () => {
    auth.login.mockRejectedValue(new HttpErrorResponse({ status: 401 }));
    await render();

    await type(input('email'), 'demo-operator@example.com');
    await type(input('password'), 'wrong');
    await signIn();

    expect(page().querySelector('[role="alert"]')?.textContent).toContain(
      'Invalid email or password',
    );
    expect(navigate).not.toHaveBeenCalled();
  });

  it('offers one-click demo logins when the server allows them', async () => {
    await render();

    const buttons = [...page().querySelectorAll<HTMLButtonElement>('.demo button')];
    expect(buttons.map((button) => button.textContent?.trim())).toEqual([
      'Admin, Manages vessels',
      'Operator, Monitors and handles alerts',
      'Viewer, Read-only access',
    ]);

    buttons[2].click();
    await fixture.whenStable();

    expect(auth.demoLogin).toHaveBeenCalledWith('viewer');
    expect(navigate).toHaveBeenCalledWith('/');
  });

  it('hides demo logins when the server does not allow them', async () => {
    await render({}, false);

    expect(page().querySelector('.demo')).toBeNull();
  });

  it('explains why the user was sent back to the login page', async () => {
    await render({ expired: 'true' });

    expect(page().querySelector('[role="status"]')?.textContent).toContain('session expired');
  });
});
