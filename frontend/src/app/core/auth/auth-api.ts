import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE, AUTH_BASE } from '../api/api-providers';
import {
  ApiError,
  AuthFlow,
  EmailVerificationInfo,
  LoginResult,
  Me,
  PasswordResetKeyResult,
  PasswordResetRequestResult,
  PasswordResetResult,
  SessionResult,
  SignupRequest,
  SignupResult,
  VerifyEmailResult,
} from './auth-models';

const EMAIL_VERIFICATION_KEY_HEADER = 'X-Email-Verification-Key';
const PASSWORD_RESET_KEY_HEADER = 'X-Password-Reset-Key';

/** Keys travel in a header; anything but visible ASCII cannot be sent and cannot be a valid key. */
const HEADER_SAFE = /^[\x21-\x7E]+$/;

/** What the server answers for a bad key, so unusable keys look the same as rejected ones. */
const INVALID_VERIFICATION_KEY: ApiError = {
  code: 'invalid_or_expired_key',
  message: 'The link is invalid or has expired.',
  param: 'key',
};

const INVALID_RESET_KEY: ApiError = {
  code: 'invalid_password_reset',
  message: 'The link is invalid or has expired.',
  param: 'key',
};

/** Status and body of a response whose status is an expected outcome rather than a failure. */
interface Reply {
  status: number;
  body: unknown;
}

interface FlowsBody {
  data?: { flows?: AuthFlow[] };
}

interface ErrorsBody {
  errors?: ApiError[];
}

interface EmailBody {
  data: { email: string };
}

/**
 * Thin typed wrapper around the allauth headless "browser" API and `/api/me/`.
 * allauth answers 401 for "not (fully) authenticated" and 400 for validation errors; both are
 * normal outcomes here and are returned as values. Anything else is thrown.
 */
@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);

  /** Returns the reply for statuses allauth uses for normal outcomes; rethrows everything else. */
  private async send(request: Observable<HttpResponse<unknown>>): Promise<Reply> {
    try {
      const response = await firstValueFrom(request);
      return { status: response.status, body: response.body };
    } catch (error) {
      if (error instanceof HttpErrorResponse && [400, 401, 403, 429].includes(error.status)) {
        return { status: error.status, body: error.error };
      }
      throw error;
    }
  }

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

  async signup({ email, password, invitationToken }: SignupRequest): Promise<SignupResult> {
    const reply = await this.send(
      this.http.post(
        `${AUTH_BASE}/auth/signup`,
        { email, password, invitation_token: invitationToken },
        { observe: 'response' },
      ),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'authenticated' };
      case 401:
        return { kind: 'pending', flows: flowsOf(reply.body) };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      case 403:
        return { kind: 'closed' };
      case 429:
        return { kind: 'rate_limited' };
      default:
        throw unexpected(reply);
    }
  }

  /** Looks at the link from the verification email; confirms nothing. */
  async getEmailVerification(key: string): Promise<EmailVerificationInfo> {
    if (!HEADER_SAFE.test(key)) {
      return { kind: 'invalid', errors: [INVALID_VERIFICATION_KEY] };
    }
    const reply = await this.send(
      this.http.get(`${AUTH_BASE}/auth/email/verify`, {
        headers: { [EMAIL_VERIFICATION_KEY_HEADER]: key },
        observe: 'response',
      }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'valid', email: (reply.body as EmailBody).data.email };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      default:
        throw unexpected(reply);
    }
  }

  async verifyEmail(key: string): Promise<VerifyEmailResult> {
    const reply = await this.send(
      this.http.post(`${AUTH_BASE}/auth/email/verify`, { key }, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'authenticated' };
      case 401:
        return { kind: 'verified' };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      default:
        throw unexpected(reply);
    }
  }

  async requestPasswordReset(email: string): Promise<PasswordResetRequestResult> {
    const reply = await this.send(
      this.http.post(`${AUTH_BASE}/auth/password/request`, { email }, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'sent' };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      case 429:
        return { kind: 'rate_limited' };
      default:
        throw unexpected(reply);
    }
  }

  async checkPasswordResetKey(key: string): Promise<PasswordResetKeyResult> {
    if (!HEADER_SAFE.test(key)) {
      return { kind: 'invalid', errors: [INVALID_RESET_KEY] };
    }
    const reply = await this.send(
      this.http.get(`${AUTH_BASE}/auth/password/reset`, {
        headers: { [PASSWORD_RESET_KEY_HEADER]: key },
        observe: 'response',
      }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'valid' };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      case 429:
        return { kind: 'rate_limited' };
      default:
        throw unexpected(reply);
    }
  }

  async resetPassword(key: string, password: string): Promise<PasswordResetResult> {
    const reply = await this.send(
      this.http.post(
        `${AUTH_BASE}/auth/password/reset`,
        { key, password },
        { observe: 'response' },
      ),
    );
    switch (reply.status) {
      case 200: // would mean "signed in"; either way the password has been reset
      case 401: // the normal answer: reset done, not signed in
        return { kind: 'done' };
      case 400:
        return { kind: 'invalid', errors: errorsOf(reply.body) };
      case 429:
        return { kind: 'rate_limited' };
      default:
        throw unexpected(reply);
    }
  }

  getMe(): Promise<Me> {
    return firstValueFrom(this.http.get<Me>(`${API_BASE}/me/`));
  }
}

function flowsOf(source: unknown): AuthFlow[] {
  const body = source instanceof HttpErrorResponse ? source.error : source;
  return (body as FlowsBody | null)?.data?.flows ?? [];
}

function errorsOf(body: unknown): ApiError[] {
  return (body as ErrorsBody | null)?.errors ?? [];
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
