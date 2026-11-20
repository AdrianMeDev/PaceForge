import { EnvironmentProviders } from '@angular/core';
import {
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
  provideHttpClient,
  withInterceptors,
  withXsrfConfiguration,
} from '@angular/common/http';

/** All API calls are same-origin (`/api/...`); Django's session cookie does the authentication. */
export const API_BASE = '/api';
export const AUTH_BASE = `${API_BASE}/auth/browser/v1`;

/**
 * Keeps the service worker out of the API: it caches no answer of the API anyway, and a request
 * that waits minutes for the coach should go straight to the server, so that its answer (or its
 * error) reaches the page as the server sent it.
 */
export const bypassServiceWorker: HttpInterceptorFn = (
  request: HttpRequest<unknown>,
  next: HttpHandlerFn,
) =>
  next(
    request.url.startsWith(`${API_BASE}/`)
      ? request.clone({ setHeaders: { 'ngsw-bypass': 'true' } })
      : request,
  );

/**
 * HttpClient with Django-compatible CSRF handling: Angular copies the `csrftoken` cookie into
 * the `X-CSRFToken` header of every mutating same-origin request (GET/HEAD are left alone). API
 * requests bypass the service worker.
 */
export function provideApiClient(): EnvironmentProviders {
  return provideHttpClient(
    withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
    withInterceptors([bypassServiceWorker]),
  );
}
