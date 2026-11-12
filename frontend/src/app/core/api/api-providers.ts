import { EnvironmentProviders } from '@angular/core';
import { provideHttpClient, withXsrfConfiguration } from '@angular/common/http';

/** All API calls are same-origin (`/api/...`); Django's session cookie does the authentication. */
export const API_BASE = '/api';
export const AUTH_BASE = `${API_BASE}/auth/browser/v1`;

/**
 * HttpClient with Django-compatible CSRF handling: Angular copies the `csrftoken` cookie into
 * the `X-CSRFToken` header of every mutating same-origin request (GET/HEAD are left alone).
 */
export function provideApiClient(): EnvironmentProviders {
  return provideHttpClient(
    withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
  );
}
