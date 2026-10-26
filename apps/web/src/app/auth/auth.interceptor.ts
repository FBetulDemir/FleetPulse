import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthService, SKIP_SESSION_REFRESH } from './auth.service';

/**
 * When a request fails with 401 because the access token expired, refreshes the
 * session once and retries the request. If the refresh fails, the session is over.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (request.context.get(SKIP_SESSION_REFRESH)) return next(request);

  const auth = inject(AuthService);
  return next(request).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
        return throwError(() => error);
      }
      return from(auth.refresh()).pipe(
        switchMap((refreshed) => {
          if (refreshed) return next(request);
          auth.sessionExpired();
          return throwError(() => error);
        }),
      );
    }),
  );
};
