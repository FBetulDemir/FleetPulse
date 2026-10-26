import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

/** Pages that need a logged-in user. Others are sent to login, then brought back. */
export const authGuard: CanActivateFn = async (_route, state) => {
  const router = inject(Router);
  const user = await inject(AuthService).ensureSession();
  return user ? true : router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** The login page: already logged-in users go straight to the app. */
export const guestGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const user = await inject(AuthService).ensureSession();
  return user ? router.createUrlTree(['/']) : true;
};

/** Only allows same-site paths as a post-login target, so links cannot redirect elsewhere. */
export function safeReturnUrl(url: string | null | undefined): string {
  return url && url.startsWith('/') && !url.startsWith('//') ? url : '/';
}
