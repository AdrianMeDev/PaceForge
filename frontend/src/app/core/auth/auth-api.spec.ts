import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AUTH_BASE, provideApiClient } from '../api/api-providers';
import { AuthApi } from './auth-api';

const SIGNUP = `${AUTH_BASE}/auth/signup`;
const EMAIL_VERIFY = `${AUTH_BASE}/auth/email/verify`;
const PASSWORD_REQUEST = `${AUTH_BASE}/auth/password/request`;
const PASSWORD_RESET = `${AUTH_BASE}/auth/password/reset`;

const SIGNUP_REQUEST = {
  email: 'ada@example.com',
  password: 'correct-horse',
  invitationToken: 'tok-123',
};

describe('AuthApi account calls', () => {
  let api: AuthApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(AuthApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  /** Answers the one request `action` sends and returns its result together with that request. */
  async function run<T>(
    action: Promise<T>,
    method: string,
    url: string,
    reply: string | object,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  const error = (code: string, param?: string) => ({
    status: 400,
    errors: [{ code, message: `msg ${code}`, ...(param ? { param } : {}) }],
  });

  describe('signup', () => {
    it('sends email, password and the invitation token', async () => {
      const { request } = await run(api.signup(SIGNUP_REQUEST), 'POST', SIGNUP, {}, 401);

      expect(request.request.body).toEqual({
        email: 'ada@example.com',
        password: 'correct-horse',
        invitation_token: 'tok-123',
      });
    });

    it('reports the open email verification as pending', async () => {
      const flows = [{ id: 'login' }, { id: 'verify_email', is_pending: true }];

      const { result } = await run(
        api.signup(SIGNUP_REQUEST),
        'POST',
        SIGNUP,
        { data: { flows } },
        401,
      );

      expect(result).toEqual({ kind: 'pending', flows });
    });

    it('reports a signed-in account when verification is not required', async () => {
      const { result } = await run(api.signup(SIGNUP_REQUEST), 'POST', SIGNUP, {}, 200);

      expect(result).toEqual({ kind: 'authenticated' });
    });

    it.each([
      ['invalid_invitation', 'invitation_token'],
      ['password_too_short', 'password'],
    ])('keeps the %s error with its field', async (code, param) => {
      const { result } = await run(
        api.signup(SIGNUP_REQUEST),
        'POST',
        SIGNUP,
        error(code, param),
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [{ code, message: `msg ${code}`, param }],
      });
    });

    it('reports closed registration', async () => {
      const { result } = await run(api.signup(SIGNUP_REQUEST), 'POST', SIGNUP, {}, 403);

      expect(result).toEqual({ kind: 'closed' });
    });

    it('reports the rate limit', async () => {
      const { result } = await run(api.signup(SIGNUP_REQUEST), 'POST', SIGNUP, {}, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('rejects on unexpected server errors', async () => {
      const outcome = run(api.signup(SIGNUP_REQUEST), 'POST', SIGNUP, 'boom', 500);

      await expect(outcome).rejects.toBeDefined();
    });
  });

  describe('getEmailVerification', () => {
    it('sends the key in the header and returns the address to confirm', async () => {
      const { result, request } = await run(
        api.getEmailVerification('MQ:1xRY3y:abc-_'),
        'GET',
        EMAIL_VERIFY,
        { status: 200, data: { email: 'ada@example.com' } },
        200,
      );

      expect(request.request.headers.get('X-Email-Verification-Key')).toBe('MQ:1xRY3y:abc-_');
      expect(result).toEqual({ kind: 'valid', email: 'ada@example.com' });
    });

    it('reports an invalid or expired key', async () => {
      const { result } = await run(
        api.getEmailVerification('stale'),
        'GET',
        EMAIL_VERIFY,
        error('invalid_or_expired_key', 'key'),
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          { code: 'invalid_or_expired_key', message: 'msg invalid_or_expired_key', param: 'key' },
        ],
      });
    });

    it.each(['has space', 'umlaut-ä', '€uro', '', 'line\nbreak'])(
      'treats %j as invalid without sending a request',
      async (key) => {
        const result = await api.getEmailVerification(key);

        expect(result).toEqual({
          kind: 'invalid',
          errors: [expect.objectContaining({ code: 'invalid_or_expired_key', param: 'key' })],
        });
        backend.expectNone(EMAIL_VERIFY);
      },
    );
  });

  describe('verifyEmail', () => {
    it('sends the key in the body', async () => {
      const { request } = await run(api.verifyEmail('k:1'), 'POST', EMAIL_VERIFY, {}, 401);

      expect(request.request.body).toEqual({ key: 'k:1' });
    });

    it('reports a confirmation that also signed the user in', async () => {
      const { result } = await run(api.verifyEmail('k'), 'POST', EMAIL_VERIFY, {}, 200);

      expect(result).toEqual({ kind: 'authenticated' });
    });

    it('reports a plain confirmation (401: not signed in)', async () => {
      const { result } = await run(api.verifyEmail('k'), 'POST', EMAIL_VERIFY, {}, 401);

      expect(result).toEqual({ kind: 'verified' });
    });

    it('reports an invalid or expired key', async () => {
      const { result } = await run(
        api.verifyEmail('k'),
        'POST',
        EMAIL_VERIFY,
        error('invalid_or_expired_key', 'key'),
        400,
      );

      expect(result.kind).toBe('invalid');
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(api.verifyEmail('k'), 'POST', EMAIL_VERIFY, 'boom', 500),
      ).rejects.toBeDefined();
    });
  });

  describe('requestPasswordReset', () => {
    it('sends the email address', async () => {
      const { request } = await run(
        api.requestPasswordReset('ada@example.com'),
        'POST',
        PASSWORD_REQUEST,
        {},
        200,
      );

      expect(request.request.body).toEqual({ email: 'ada@example.com' });
    });

    it('answers sent', async () => {
      const { result } = await run(
        api.requestPasswordReset('ada@example.com'),
        'POST',
        PASSWORD_REQUEST,
        {},
        200,
      );

      expect(result).toEqual({ kind: 'sent' });
    });

    it('keeps validation errors', async () => {
      const { result } = await run(
        api.requestPasswordReset('nope'),
        'POST',
        PASSWORD_REQUEST,
        error('invalid', 'email'),
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [{ code: 'invalid', message: 'msg invalid', param: 'email' }],
      });
    });

    it('reports the rate limit', async () => {
      const { result } = await run(
        api.requestPasswordReset('a@example.com'),
        'POST',
        PASSWORD_REQUEST,
        {},
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('rejects on unexpected server errors', async () => {
      const outcome = run(
        api.requestPasswordReset('a@example.com'),
        'POST',
        PASSWORD_REQUEST,
        'boom',
        500,
      );

      await expect(outcome).rejects.toBeDefined();
    });
  });

  describe('checkPasswordResetKey', () => {
    it('sends the key in the header', async () => {
      const { result, request } = await run(
        api.checkPasswordResetKey('abc-123'),
        'GET',
        PASSWORD_RESET,
        { status: 200, data: { user: {} } },
        200,
      );

      expect(request.request.headers.get('X-Password-Reset-Key')).toBe('abc-123');
      expect(result).toEqual({ kind: 'valid' });
    });

    it('reports an invalid or expired key', async () => {
      const { result } = await run(
        api.checkPasswordResetKey('stale'),
        'GET',
        PASSWORD_RESET,
        error('invalid_password_reset', 'key'),
        400,
      );

      expect(result.kind).toBe('invalid');
    });

    it('reports the rate limit', async () => {
      const { result } = await run(api.checkPasswordResetKey('k'), 'GET', PASSWORD_RESET, {}, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('treats a key that cannot be a header value as invalid without a request', async () => {
      const result = await api.checkPasswordResetKey('ünïcode key');

      expect(result).toEqual({
        kind: 'invalid',
        errors: [expect.objectContaining({ code: 'invalid_password_reset', param: 'key' })],
      });
      backend.expectNone(PASSWORD_RESET);
    });
  });

  describe('resetPassword', () => {
    it('sends key and new password in the body', async () => {
      const { request } = await run(
        api.resetPassword('k-1', 'new-secret'),
        'POST',
        PASSWORD_RESET,
        {},
        401,
      );

      expect(request.request.body).toEqual({ key: 'k-1', password: 'new-secret' });
    });

    it.each([401, 200])('is done on status %i (a reset never needs a sign-in)', async (status) => {
      const { result } = await run(
        api.resetPassword('k', 'pw'),
        'POST',
        PASSWORD_RESET,
        {},
        status,
      );

      expect(result).toEqual({ kind: 'done' });
    });

    it('keeps key and password errors by field', async () => {
      const errors = [
        { code: 'password_too_common', message: 'Too common.', param: 'password' },
        { code: 'invalid_or_expired_key', message: 'Expired.', param: 'key' },
      ];

      const { result } = await run(
        api.resetPassword('k', 'password'),
        'POST',
        PASSWORD_RESET,
        { status: 400, errors },
        400,
      );

      expect(result).toEqual({ kind: 'invalid', errors });
    });

    it('reports the rate limit', async () => {
      const { result } = await run(api.resetPassword('k', 'pw'), 'POST', PASSWORD_RESET, {}, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(api.resetPassword('k', 'pw'), 'POST', PASSWORD_RESET, 'boom', 500),
      ).rejects.toBeDefined();
    });
  });
});
