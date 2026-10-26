import { HttpClient, HttpContext, HttpContextToken } from '@angular/common/http';
import { Service, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Role, User } from '../api/models';

const AUTH_URL = '/api/v1/auth';

/** Marks requests the interceptor must not retry after a refresh (the auth calls themselves). */
export const SKIP_SESSION_REFRESH = new HttpContextToken<boolean>(() => false);
const skipRefresh = () => new HttpContext().set(SKIP_SESSION_REFRESH, true);

/**
 * The logged-in user and the session around it.
 *
 * Tokens live in httpOnly cookies that this code never sees; the browser sends them.
 * This service only tracks who is logged in and drives login, refresh and logout.
 */
@Service()
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  /** undefined until the first session check finishes; null when logged out. */
  private readonly userSignal = signal<User | null | undefined>(undefined);
  readonly user = computed(() => this.userSignal() ?? null);

  private sessionCheck: Promise<User | null> | null = null;
  private refreshInFlight: Promise<boolean> | null = null;

  /** Who is logged in, checked with the server once per page load. Used by route guards. */
  ensureSession(): Promise<User | null> {
    const known = this.userSignal();
    if (known !== undefined) return Promise.resolve(known);
    // The interceptor refreshes an expired access token and retries, so a user with a
    // valid refresh token is still logged in after a reload.
    this.sessionCheck ??= firstValueFrom(this.http.get<User>(`${AUTH_URL}/me`)).then(
      (user) => this.setUser(user),
      () => this.setUser(null),
    );
    return this.sessionCheck;
  }

  async login(email: string, password: string): Promise<User> {
    const request = this.http.post<User>(
      `${AUTH_URL}/login`,
      { email, password },
      { context: skipRefresh() },
    );
    return this.setUser(await firstValueFrom(request)) as User;
  }

  async demoLogin(role: Role): Promise<User> {
    const request = this.http.post<User>(
      `${AUTH_URL}/demo-login`,
      { role },
      { context: skipRefresh() },
    );
    return this.setUser(await firstValueFrom(request)) as User;
  }

  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.post(`${AUTH_URL}/logout`, null, { context: skipRefresh() }));
    } finally {
      this.setUser(null);
      await this.router.navigateByUrl('/login');
    }
  }

  /**
   * Gets a new access token. Only one refresh runs at a time: every rotation invalidates
   * the previous refresh token, so two parallel refreshes would look like token theft
   * to the server and end the session. The Web Locks API extends this across tabs.
   */
  refresh(): Promise<boolean> {
    this.refreshInFlight ??= withLock('fleetpulse-session-refresh', () =>
      firstValueFrom(this.http.post<User>(`${AUTH_URL}/refresh`, null, { context: skipRefresh() })),
    )
      .then((user) => {
        this.setUser(user);
        return true;
      })
      .catch(() => false)
      .finally(() => (this.refreshInFlight = null));
    return this.refreshInFlight;
  }

  /** The session ended on the server. Sends a previously logged-in user to the login page. */
  sessionExpired(): void {
    const wasLoggedIn = this.userSignal() != null;
    this.setUser(null);
    if (wasLoggedIn) {
      void this.router.navigate(['/login'], {
        queryParams: { returnUrl: this.router.url, expired: true },
      });
    }
  }

  private setUser(user: User | null): User | null {
    this.userSignal.set(user);
    return user;
  }
}

function withLock<T>(name: string, task: () => Promise<T>): Promise<T> {
  // Not available in every environment (e.g. older browsers, jsdom in tests).
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks;
  return locks ? locks.request(name, task) : task();
}
