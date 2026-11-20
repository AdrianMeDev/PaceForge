import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE, AUTH_BASE, provideApiClient } from '../api/api-providers';
import { AccountExportResult } from './auth-models';
import { AuthApi } from './auth-api';

const EXPORT = `${API_BASE}/me/export/`;
const SIGNUP = `${AUTH_BASE}/auth/signup`;
const EMAIL_VERIFY = `${AUTH_BASE}/auth/email/verify`;
const PASSWORD_REQUEST = `${AUTH_BASE}/auth/password/request`;
const PASSWORD_RESET = `${AUTH_BASE}/auth/password/reset`;

const MFA_AUTHENTICATE = `${AUTH_BASE}/auth/2fa/authenticate`;
const REAUTHENTICATE = `${AUTH_BASE}/auth/reauthenticate`;
const TOTP = `${AUTH_BASE}/account/authenticators/totp`;
const RECOVERY_CODES = `${AUTH_BASE}/account/authenticators/recovery-codes`;

/** Signed in, but the password has to be confirmed again for this action. */
const REAUTHENTICATION_REQUIRED = {
  status: 401,
  data: {
    flows: [
      { id: 'reauthenticate' },
      { id: 'reauthenticate_by_code', recipients: [{ email: 'ada@example.com' }] },
      { id: 'mfa_reauthenticate', types: ['totp'] },
    ],
  },
  meta: { is_authenticated: true },
};

/** Not signed in at all: also a 401, but nothing to confirm. */
const SIGNED_OUT = {
  status: 401,
  data: { flows: [{ id: 'login' }, { id: 'signup' }] },
  meta: { is_authenticated: null },
};

const CODES = {
  status: 200,
  data: {
    type: 'recovery_codes',
    total_code_count: 10,
    unused_code_count: 2,
    unused_codes: ['11111111', '22222222'],
  },
};

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

  describe('authenticateMfa', () => {
    it('sends the code (an authenticator code or a recovery code) in the body', async () => {
      const { request } = await run(
        api.authenticateMfa('123456'),
        'POST',
        MFA_AUTHENTICATE,
        {},
        200,
      );

      expect(request.request.body).toEqual({ code: '123456' });
    });

    it('reports a completed sign-in', async () => {
      const { result } = await run(
        api.authenticateMfa('123456'),
        'POST',
        MFA_AUTHENTICATE,
        {},
        200,
      );

      expect(result).toEqual({ kind: 'authenticated' });
    });

    it.each(['incorrect_code', 'too_many_login_attempts'])(
      'keeps the %s error with its field',
      async (code) => {
        const { result } = await run(
          api.authenticateMfa('000000'),
          'POST',
          MFA_AUTHENTICATE,
          error(code, 'code'),
          400,
        );

        expect(result).toEqual({
          kind: 'invalid',
          errors: [{ code, message: `msg ${code}`, param: 'code' }],
        });
      },
    );

    it('reports that the half-finished sign-in is gone', async () => {
      const { result } = await run(
        api.authenticateMfa('123456'),
        'POST',
        MFA_AUTHENTICATE,
        SIGNED_OUT,
        401,
      );

      expect(result).toEqual({ kind: 'expired' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(api.authenticateMfa('1'), 'POST', MFA_AUTHENTICATE, 'boom', 500),
      ).rejects.toBeDefined();
    });
  });

  describe('reauthenticate', () => {
    it('sends the password in the body and reports the confirmation', async () => {
      const { result, request } = await run(
        api.reauthenticate('secret'),
        'POST',
        REAUTHENTICATE,
        {},
        200,
      );

      expect(request.request.body).toEqual({ password: 'secret' });
      expect(result).toEqual({ kind: 'confirmed' });
    });

    it('keeps the error for a wrong password', async () => {
      const { result } = await run(
        api.reauthenticate('nope'),
        'POST',
        REAUTHENTICATE,
        error('incorrect_password', 'password'),
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          { code: 'incorrect_password', message: 'msg incorrect_password', param: 'password' },
        ],
      });
    });

    it('reports the rate limit', async () => {
      const { result } = await run(api.reauthenticate('x'), 'POST', REAUTHENTICATE, {}, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });
  });

  describe('getTotp', () => {
    it('reads the secret and the authenticator URL from the 404 answer when none is active', async () => {
      const meta = {
        secret: 'JBSWY3DP',
        totp_url: 'otpauth://totp/ada%40example.com?secret=JBSWY3DP&issuer=PaceForge',
      };

      const { result } = await run(api.getTotp(), 'GET', TOTP, { status: 404, meta }, 404);

      expect(result).toEqual({ kind: 'inactive', secret: 'JBSWY3DP', totpUrl: meta.totp_url });
    });

    it('describes an active authenticator', async () => {
      const { result } = await run(
        api.getTotp(),
        'GET',
        TOTP,
        { status: 200, data: { type: 'totp', created_at: 1794510610.1, last_used_at: null } },
        200,
      );

      expect(result).toEqual({ kind: 'active', createdAt: 1794510610.1, lastUsedAt: null });
    });

    it('does not mistake a 404 without setup data for "not active"', async () => {
      await expect(run(api.getTotp(), 'GET', TOTP, { status: 404 }, 404)).rejects.toBeDefined();
    });

    it('rejects when the visitor is signed out', async () => {
      await expect(run(api.getTotp(), 'GET', TOTP, SIGNED_OUT, 401)).rejects.toBeDefined();
    });
  });

  describe('activateTotp', () => {
    it('sends the code and reports the activation', async () => {
      const { result, request } = await run(
        api.activateTotp('123456'),
        'POST',
        TOTP,
        { status: 200 },
        200,
      );

      expect(request.request.body).toEqual({ code: '123456' });
      expect(result).toEqual({ kind: 'activated' });
    });

    it('keeps the error for a wrong code', async () => {
      const { result } = await run(
        api.activateTotp('000000'),
        'POST',
        TOTP,
        error('incorrect_code', 'code'),
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [{ code: 'incorrect_code', message: 'msg incorrect_code', param: 'code' }],
      });
    });

    it('asks for the password when the server wants it confirmed again', async () => {
      const { result } = await run(
        api.activateTotp('123456'),
        'POST',
        TOTP,
        REAUTHENTICATION_REQUIRED,
        401,
      );

      expect(result).toEqual({ kind: 'reauthentication_required' });
    });

    it('asks for the password only for a signed-in user, whatever the flows say', async () => {
      const notSignedIn = {
        status: 401,
        data: { flows: [{ id: 'reauthenticate' }] },
        meta: { is_authenticated: false },
      };

      await expect(
        run(api.activateTotp('123456'), 'POST', TOTP, notSignedIn, 401),
      ).rejects.toBeDefined();
    });

    it('does not take a signed-out 401 for a password prompt', async () => {
      await expect(
        run(api.activateTotp('123456'), 'POST', TOTP, SIGNED_OUT, 401),
      ).rejects.toBeDefined();
    });
  });

  describe('deactivateTotp', () => {
    it('reports the removal', async () => {
      const { result } = await run(api.deactivateTotp(), 'DELETE', TOTP, { status: 200 }, 200);

      expect(result).toEqual({ kind: 'deactivated' });
    });

    it('asks for the password when the server wants it confirmed again', async () => {
      const { result } = await run(
        api.deactivateTotp(),
        'DELETE',
        TOTP,
        REAUTHENTICATION_REQUIRED,
        401,
      );

      expect(result).toEqual({ kind: 'reauthentication_required' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.deactivateTotp(), 'DELETE', TOTP, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('getRecoveryCodes', () => {
    it('returns the unused codes with their counts', async () => {
      const { result } = await run(api.getRecoveryCodes(), 'GET', RECOVERY_CODES, CODES, 200);

      expect(result).toEqual({
        kind: 'codes',
        codes: ['11111111', '22222222'],
        total: 10,
        unused: 2,
      });
    });

    it('returns no codes when the server does not list them', async () => {
      const hidden = { status: 200, data: { total_code_count: 10, unused_code_count: 10 } };

      const { result } = await run(api.getRecoveryCodes(), 'GET', RECOVERY_CODES, hidden, 200);

      expect(result).toEqual({ kind: 'codes', codes: [], total: 10, unused: 10 });
    });

    it('reports that there are none (no authenticator set up)', async () => {
      const { result } = await run(
        api.getRecoveryCodes(),
        'GET',
        RECOVERY_CODES,
        { status: 404 },
        404,
      );

      expect(result).toEqual({ kind: 'none' });
    });

    it('asks for the password when the server wants it confirmed again', async () => {
      const { result } = await run(
        api.getRecoveryCodes(),
        'GET',
        RECOVERY_CODES,
        REAUTHENTICATION_REQUIRED,
        401,
      );

      expect(result).toEqual({ kind: 'reauthentication_required' });
    });
  });

  describe('regenerateRecoveryCodes', () => {
    it('posts an empty body and returns the new codes', async () => {
      const { result, request } = await run(
        api.regenerateRecoveryCodes(),
        'POST',
        RECOVERY_CODES,
        CODES,
        200,
      );

      expect(request.request.body).toEqual({});
      expect(result).toEqual({
        kind: 'regenerated',
        codes: ['11111111', '22222222'],
        total: 10,
        unused: 2,
      });
    });

    it('asks for the password when the server wants it confirmed again', async () => {
      const { result } = await run(
        api.regenerateRecoveryCodes(),
        'POST',
        RECOVERY_CODES,
        REAUTHENTICATION_REQUIRED,
        401,
      );

      expect(result).toEqual({ kind: 'reauthentication_required' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(api.regenerateRecoveryCodes(), 'POST', RECOVERY_CODES, 'boom', 500),
      ).rejects.toBeDefined();
    });
  });

  describe('exportAccountData', () => {
    const DISPOSITION = 'attachment; filename="paceforge-export-2026-11-20.json"';

    /** The export is a file, so the answer is flushed as a blob with the given headers. */
    async function exportWith(
      status: number,
      headers: Record<string, string> = {},
    ): Promise<AccountExportResult> {
      const action = api.exportAccountData();
      const request = await vi.waitFor(() =>
        backend.expectOne((req) => req.method === 'GET' && req.url === EXPORT),
      );
      expect(request.request.responseType).toBe('blob');
      request.flush(new Blob(['{}'], { type: 'application/json' }), {
        status,
        statusText: `HTTP ${status}`,
        headers,
      });
      return action;
    }

    it('returns the file with the name the server suggests', async () => {
      const result = await exportWith(200, { 'Content-Disposition': DISPOSITION });

      expect(result).toEqual({
        kind: 'exported',
        file: expect.any(Blob),
        filename: 'paceforge-export-2026-11-20.json',
      });
    });

    it.each([
      ['no Content-Disposition header', {}],
      ['a header without a file name', { 'Content-Disposition': 'attachment' }],
      ['a file name with a path', { 'Content-Disposition': 'attachment; filename="../x.json"' }],
      ['a hidden file name', { 'Content-Disposition': 'attachment; filename=".env"' }],
      ['a file name with spaces', { 'Content-Disposition': 'attachment; filename="a b.json"' }],
    ])('falls back to a fixed file name for %s', async (_case, headers) => {
      const result = await exportWith(200, headers);

      expect(result).toMatchObject({ kind: 'exported', filename: 'paceforge-export.json' });
    });

    it('reports a request without a signed-in user', async () => {
      expect(await exportWith(403)).toEqual({ kind: 'forbidden' });
    });

    it('reports the rate limit', async () => {
      expect(await exportWith(429)).toEqual({ kind: 'rate_limited' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(exportWith(500)).rejects.toBeDefined();
    });
  });

  describe('deleteAccount', () => {
    const DELETE_ACCOUNT = `${API_BASE}/me/delete/`;

    it('sends the confirmation, the password and the code; reports the deletion', async () => {
      const { result, request } = await run(
        api.deleteAccount({
          confirmation: 'ada@example.com',
          password: 'correct-horse',
          mfaCode: '123456',
        }),
        'POST',
        DELETE_ACCOUNT,
        '',
        204,
      );

      expect(request.request.body).toEqual({
        confirmation: 'ada@example.com',
        password: 'correct-horse',
        mfa_code: '123456',
      });
      expect(result).toEqual({ kind: 'deleted' });
    });

    it('sends an empty code when the account has no authenticator app', async () => {
      const { request } = await run(
        api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
        'POST',
        DELETE_ACCOUNT,
        '',
        204,
      );

      expect(request.request.body).toEqual({
        confirmation: 'ada@example.com',
        password: 'correct-horse',
        mfa_code: '',
      });
    });

    it('keeps the field errors, one per field', async () => {
      const { result } = await run(
        api.deleteAccount({ confirmation: 'ada@example.com', password: 'wrong' }),
        'POST',
        DELETE_ACCOUNT,
        {
          password: ['The password is wrong.'],
          mfa_code: ['A code from your authenticator app is required.'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          { code: 'invalid', message: 'The password is wrong.', param: 'password' },
          {
            code: 'invalid',
            message: 'A code from your authenticator app is required.',
            param: 'mfa_code',
          },
        ],
      });
    });

    it('reports a request without a signed-in user', async () => {
      const { result } = await run(
        api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
        'POST',
        DELETE_ACCOUNT,
        {},
        403,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('reports that the last administrator cannot be deleted', async () => {
      const { result } = await run(
        api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
        'POST',
        DELETE_ACCOUNT,
        { detail: 'The last administrator cannot be deleted.', code: 'last_admin' },
        409,
      );

      expect(result).toEqual({ kind: 'last_admin' });
    });

    it('rejects a conflict that is not about the last administrator', async () => {
      await expect(
        run(
          api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
          'POST',
          DELETE_ACCOUNT,
          { detail: 'Something else.' },
          409,
        ),
      ).rejects.toBeDefined();
    });

    it('reports the rate limit', async () => {
      const { result } = await run(
        api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
        'POST',
        DELETE_ACCOUNT,
        {},
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(
          api.deleteAccount({ confirmation: 'ada@example.com', password: 'correct-horse' }),
          'POST',
          DELETE_ACCOUNT,
          'boom',
          500,
        ),
      ).rejects.toBeDefined();
    });
  });
});
