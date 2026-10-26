import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { user } from '../../testing/users';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

const ME = '/api/v1/auth/me';
const REFRESH = '/api/v1/auth/refresh';
const UNAUTHORIZED = { status: 401, statusText: 'Unauthorized' };

describe('AuthService with the auth interceptor', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  /** Lets pending promise callbacks run (e.g. the retry after a refresh). */
  const settle = () => new Promise((resolve) => setTimeout(resolve));

  it('restores the session from the server', async () => {
    const session = auth.ensureSession();
    http.expectOne(ME).flush(user());

    expect(await session).toEqual(user());
    expect(auth.user()).toEqual(user());
  });

  it('refreshes an expired access token and retries the request', async () => {
    const session = auth.ensureSession();

    http.expectOne(ME).flush(null, UNAUTHORIZED);
    await settle();
    http.expectOne(REFRESH).flush(user());
    await settle();
    http.expectOne(ME).flush(user());

    expect(await session).toEqual(user());
  });

  it('is logged out when the refresh fails too', async () => {
    const navigate = vi.spyOn(router, 'navigate');
    const session = auth.ensureSession();

    http.expectOne(ME).flush(null, UNAUTHORIZED);
    await settle();
    http.expectOne(REFRESH).flush(null, UNAUTHORIZED);

    expect(await session).toBeNull();
    // Nobody was logged in before, so the route guard decides where to go, not this.
    expect(navigate).not.toHaveBeenCalled();
  });

  it('runs only one refresh at a time', async () => {
    const results = Promise.all([auth.refresh(), auth.refresh(), auth.refresh()]);
    await settle();

    http.expectOne(REFRESH).flush(user());

    expect(await results).toEqual([true, true, true]);
  });

  it('sends a logged-in user to the login page when their session ends', async () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const login = auth.login('demo-operator@example.com', 'secret');
    http.expectOne('/api/v1/auth/login').flush(user());
    await login;

    const request = firstValueFrom(TestBed.inject(HttpClient).get('/api/v1/vessels'));
    http.expectOne('/api/v1/vessels').flush(null, UNAUTHORIZED);
    await settle();
    http.expectOne(REFRESH).flush(null, UNAUTHORIZED);

    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(auth.user()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login'], expect.objectContaining({}));
  });

  it('does not try to refresh when the login itself fails', async () => {
    const login = auth.login('demo-operator@example.com', 'wrong');
    http.expectOne('/api/v1/auth/login').flush(null, UNAUTHORIZED);

    await expect(login).rejects.toMatchObject({ status: 401 });
    http.expectNone(REFRESH);
  });

  it('logs out on the server and goes to the login page', async () => {
    const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    const logout = auth.logout();
    http.expectOne('/api/v1/auth/logout').flush(null, { status: 204, statusText: 'No Content' });
    await logout;

    expect(auth.user()).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
  });
});
