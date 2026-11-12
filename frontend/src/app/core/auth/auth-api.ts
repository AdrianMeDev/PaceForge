import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { API_BASE, AUTH_BASE } from '../api/api-providers';
import { ApiError, AuthFlow, LoginResult, Me, SessionResult } from './auth-models';

interface FlowsBody {
  data?: { flows?: AuthFlow[] };
}

interface ErrorsBody {
  errors?: ApiError[];
}

/**
 * Thin typed wrapper around the allauth headless "browser" API and `/api/me/`.
 * allauth answers 401 for "not (fully) authenticated" and 400 for validation errors; both are
 * normal outcomes here and are returned as values. Anything else is thrown.
 */
@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);

  /** Makes Django set the `csrftoken` cookie, which later POST/DELETE requests depend on. */
  async loadConfig(): Promise<void> {
    await firstValueFrom(this.http.get(`${AUTH_BASE}/config`));
  }

  async getSession(): Promise<SessionResult> {
    try {
      await firstValueFrom(this.http.get(`${AUTH_BASE}/auth/session`));
      return { kind: 'authenticated' };
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        return { kind: 'anonymous', flows: flowsOf(error) };
      }
      throw error;
    }
  }

  async login(email: string, password: string): Promise<LoginResult> {
    try {
      await firstValueFrom(this.http.post(`${AUTH_BASE}/auth/login`, { email, password }));
      return { kind: 'authenticated' };
    } catch (error) {
      if (error instanceof HttpErrorResponse) {
        if (error.status === 401) {
          return { kind: 'pending', flows: flowsOf(error) };
        }
        if (error.status === 400) {
          return { kind: 'invalid', errors: (error.error as ErrorsBody | null)?.errors ?? [] };
        }
      }
      throw error;
    }
  }

  /** A successful logout is answered with 401 ("no longer authenticated"). */
  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.delete(`${AUTH_BASE}/auth/session`));
    } catch (error) {
      if (!(error instanceof HttpErrorResponse && error.status === 401)) {
        throw error;
      }
    }
  }

  getMe(): Promise<Me> {
    return firstValueFrom(this.http.get<Me>(`${API_BASE}/me/`));
  }
}

function flowsOf(error: HttpErrorResponse): AuthFlow[] {
  return (error.error as FlowsBody | null)?.data?.flows ?? [];
}
