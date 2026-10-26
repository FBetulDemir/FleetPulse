import { HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormField, email, form, required, submit } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthOptions, Role } from '../api/models';
import { safeReturnUrl } from './auth.guards';
import { AuthService } from './auth.service';

export const AUTH_OPTIONS_URL = '/api/v1/auth/options';

const DEMO_ROLES: { role: Role; label: string; description: string }[] = [
  { role: 'admin', label: 'Admin', description: 'Manages vessels' },
  { role: 'operator', label: 'Operator', description: 'Monitors and handles alerts' },
  { role: 'viewer', label: 'Viewer', description: 'Read-only access' },
];

@Component({
  selector: 'app-login-page',
  imports: [FormField, MatButtonModule, MatFormFieldModule, MatInputModule],
  templateUrl: './login-page.html',
  styleUrl: './login-page.scss',
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly query = inject(ActivatedRoute).snapshot.queryParamMap;

  protected readonly options = httpResource<AuthOptions>(() => AUTH_OPTIONS_URL);
  protected readonly demoRoles = DEMO_ROLES;
  protected readonly sessionExpired = this.query.has('expired');

  protected readonly credentials = signal({ email: '', password: '' });
  protected readonly loginForm = form(this.credentials, (field) => {
    required(field.email, { message: 'Enter your email address' });
    email(field.email, { message: 'Enter a valid email address' });
    required(field.password, { message: 'Enter your password' });
  });

  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async signIn(event: Event): Promise<void> {
    event.preventDefault();
    // submit() marks every field as touched and only runs the action if the form is valid.
    await submit(this.loginForm, async () => {
      const { email, password } = this.credentials();
      await this.run(() => this.auth.login(email, password));
      return undefined;
    });
  }

  protected demoLogin(role: Role): Promise<void> {
    return this.run(() => this.auth.demoLogin(role));
  }

  private async run(login: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await login();
      await this.router.navigateByUrl(safeReturnUrl(this.query.get('returnUrl')));
    } catch (error) {
      this.error.set(loginErrorMessage(error));
    } finally {
      this.busy.set(false);
    }
  }
}

function loginErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 401) return 'Invalid email or password.';
    if (error.status === 0) return 'Cannot reach the server. Check your connection.';
  }
  return 'Sign-in failed. Please try again.';
}
