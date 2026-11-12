import {
  provideHttpClientTesting,
  HttpTestingController,
  TestRequest,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AUTH_BASE, provideApiClient } from '../api/api-providers';
import { AuthStore } from './auth-store';

const CONFIG = `${AUTH_BASE}/config`;
const SESSION = `${AUTH_BASE}/auth/session`;
const LOGIN = `${AUTH_BASE}/auth/login`;
const ME = '/api/me/';

const ADA = { id: '1', email: 'ada@example.com', display_name: 'Ada', is_staff: false };
const UNAUTHENTICATED = {
  status: 401,
  data: { flows: [{ id: 'login' }] },
  meta: { is_authenticated: false },
};

describe('AuthStore', () => {
  let store: AuthStore;
  let backend: HttpTestingController;

  /** The store issues its requests one after another, so wait until the next one shows up. */
  function nextRequest(method: string, url: string): Promise<TestRequest> {
    return vi.waitFor(() => backend.expectOne((req) => req.method === method && req.url === url));
  }

  async function respond(
    method: string,
    url: string,
    body: string | object,
    status = 200,
  ): Promise<void> {
    (await nextRequest(method, url)).flush(body, { status, statusText: `HTTP ${status}` });
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    store = TestBed.inject(AuthStore);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  describe('initialize', () => {
    it('starts in the loading state', () => {
      expect(store.status()).toBe('loading');
    });

    it('becomes anonymous when the server reports no session', async () => {
      const done = store.initialize();
      await respond('GET', CONFIG, {});
      await respond('GET', SESSION, UNAUTHENTICATED, 401);
      await done;

      expect(store.status()).toBe('anonymous');
      expect(store.user()).toBeNull();
      expect(store.isAuthenticated()).toBe(false);
    });

    it('restores an existing session and loads the user', async () => {
      const done = store.initialize();
      await respond('GET', CONFIG, {});
      await respond('GET', SESSION, { status: 200, meta: { is_authenticated: true } });
      await respond('GET', ME, ADA);
      await done;

      expect(store.status()).toBe('authenticated');
      expect(store.user()).toEqual(ADA);
      expect(store.isStaff()).toBe(false);
    });

    it('reports unavailable instead of rejecting when the backend fails', async () => {
      const done = store.initialize();
      await respond('GET', CONFIG, 'boom', 500);

      await expect(done).resolves.toBeUndefined();
      expect(store.status()).toBe('unavailable');
    });
  });

  describe('login', () => {
    it('loads the user after a successful login', async () => {
      const outcome = store.login('ada@example.com', 'secret');
      await respond('POST', LOGIN, { status: 200, meta: { is_authenticated: true } });
      await respond('GET', ME, { ...ADA, is_staff: true });

      expect(await outcome).toEqual({ kind: 'success' });
      expect(store.status()).toBe('authenticated');
      expect(store.user()?.email).toBe('ada@example.com');
      expect(store.isStaff()).toBe(true);
    });

    it('sends the credentials in the request body', async () => {
      const outcome = store.login('ada@example.com', 'secret');
      const request = await nextRequest('POST', LOGIN);
      expect(request.request.body).toEqual({ email: 'ada@example.com', password: 'secret' });
      request.flush({}, { status: 400, statusText: 'Bad Request' });
      await outcome;
    });

    it('exposes the pending verify_email flow without logging in', async () => {
      const outcome = store.login('new@example.com', 'secret');
      await respond(
        'POST',
        LOGIN,
        {
          status: 401,
          data: { flows: [{ id: 'login' }, { id: 'verify_email', is_pending: true }] },
        },
        401,
      );

      expect(await outcome).toEqual({
        kind: 'pending',
        flows: [{ id: 'login' }, { id: 'verify_email', is_pending: true }],
      });
      expect(store.status()).toBe('anonymous');
      expect(store.pendingFlows()).toEqual([{ id: 'verify_email', is_pending: true }]);
    });

    it.each([
      ['email_password_mismatch', 'password'],
      ['too_many_login_attempts', undefined],
    ])('returns the %s error with its code and field', async (code, param) => {
      const error = { code, message: 'nope', ...(param ? { param } : {}) };
      const outcome = store.login('ada@example.com', 'wrong');
      await respond('POST', LOGIN, { status: 400, errors: [error] }, 400);

      expect(await outcome).toEqual({ kind: 'invalid', errors: [error] });
      expect(store.status()).toBe('loading');
      expect(store.user()).toBeNull();
    });

    it('rejects on unexpected server errors', async () => {
      const outcome = store.login('ada@example.com', 'secret');
      const assertion = expect(outcome).rejects.toBeDefined();
      await respond('POST', LOGIN, 'boom', 500);

      await assertion;
    });
  });

  describe('verifyEmail', () => {
    const VERIFY = `${AUTH_BASE}/auth/email/verify`;

    it('loads the user when the confirmation also signed them in', async () => {
      const outcome = store.verifyEmail('key-1');
      const request = await nextRequest('POST', VERIFY);
      expect(request.request.body).toEqual({ key: 'key-1' });
      request.flush({ status: 200 }, { status: 200, statusText: 'OK' });
      await respond('GET', ME, ADA);

      expect(await outcome).toEqual({ kind: 'authenticated' });
      expect(store.status()).toBe('authenticated');
      expect(store.user()).toEqual(ADA);
    });

    it('leaves the visitor anonymous after a plain confirmation (401)', async () => {
      const outcome = store.verifyEmail('key-1');
      await respond('POST', VERIFY, UNAUTHENTICATED, 401);

      expect(await outcome).toEqual({ kind: 'verified' });
      expect(store.user()).toBeNull();
      expect(store.isAuthenticated()).toBe(false);
    });

    it('returns the errors for an invalid or expired key', async () => {
      const error = { code: 'invalid_or_expired_key', message: 'Expired.', param: 'key' };
      const outcome = store.verifyEmail('stale');
      await respond('POST', VERIFY, { status: 400, errors: [error] }, 400);

      expect(await outcome).toEqual({ kind: 'invalid', errors: [error] });
      expect(store.user()).toBeNull();
    });
  });

  describe('logout', () => {
    it('clears the user; allauth confirms logout with a 401', async () => {
      const login = store.login('ada@example.com', 'secret');
      await respond('POST', LOGIN, {});
      await respond('GET', ME, ADA);
      await login;

      const logout = store.logout();
      await respond('DELETE', SESSION, UNAUTHENTICATED, 401);
      await logout;

      expect(store.status()).toBe('anonymous');
      expect(store.user()).toBeNull();
      expect(store.pendingFlows()).toEqual([]);
    });
  });
});
