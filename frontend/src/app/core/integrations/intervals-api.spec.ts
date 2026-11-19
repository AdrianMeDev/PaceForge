import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { IntervalsConnectionApi } from './intervals-api';
import { IntervalsConnection } from './intervals-models';

const URL = '/api/integrations/intervals/';
const CHECK = `${URL}check/`;
const KEY = 'k3y-0123456789-abcdefghij';

const CONNECTED = {
  connected: true,
  status: 'connected',
  athlete_id: 'i555',
  connected_at: '2026-11-12T23:29:46.406260Z',
  last_checked_at: '2026-11-12T23:29:46.432072Z',
  last_sync_at: null,
  last_sync_error: '',
};
const CONNECTION: IntervalsConnection = {
  status: 'connected',
  athlete_id: 'i555',
  connected_at: '2026-11-12T23:29:46.406260Z',
  last_checked_at: '2026-11-12T23:29:46.432072Z',
  last_sync_at: null,
  last_sync_error: '',
};

const UNAVAILABLE = {
  detail: 'Intervals.icu cannot be reached right now. Please try again later.',
};
const ODD_ANSWER = {
  detail: 'Intervals.icu answered in an unexpected way. Please try again later.',
};
const THROTTLED = { detail: 'Request was throttled. Expected available in 60 seconds.' };
const NO_SESSION = { detail: 'Authentication credentials were not provided.' };

describe('IntervalsConnectionApi', () => {
  let api: IntervalsConnectionApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(IntervalsConnectionApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    method: string,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  describe('get', () => {
    it('says when there is no connection', async () => {
      const { result } = await run(api.get(), 'GET', URL, { connected: false }, 200);

      expect(result).toEqual({ kind: 'not_connected' });
    });

    it('returns the connection', async () => {
      const { result } = await run(api.get(), 'GET', URL, CONNECTED, 200);

      expect(result).toEqual({ kind: 'connected', connection: CONNECTION });
    });

    it('passes on an invalid status', async () => {
      const { result } = await run(api.get(), 'GET', URL, { ...CONNECTED, status: 'invalid' }, 200);

      expect(result).toEqual({
        kind: 'connected',
        connection: { ...CONNECTION, status: 'invalid' },
      });
    });

    it('takes over only the known fields', async () => {
      const { result } = await run(
        api.get(),
        'GET',
        URL,
        { ...CONNECTED, api_key: KEY, email: 'private@example.com' },
        200,
      );

      expect(Object.keys((result as { connection: object }).connection).sort()).toEqual([
        'athlete_id',
        'connected_at',
        'last_checked_at',
        'last_sync_at',
        'last_sync_error',
        'status',
      ]);
      expect(JSON.stringify(result)).not.toContain(KEY);
    });

    it.each(['', 'invalid_key', 'unavailable', 'unexpected'] as const)(
      'parses last_sync_at and last_sync_error (%j)',
      async (last_sync_error) => {
        const last_sync_at = '2026-11-13T08:15:00Z';
        const { result } = await run(
          api.get(),
          'GET',
          URL,
          { ...CONNECTED, last_sync_at, last_sync_error },
          200,
        );

        expect(result).toEqual({
          kind: 'connected',
          connection: { ...CONNECTION, last_sync_at, last_sync_error },
        });
      },
    );

    it.each([401, 403])('reports a lost session (%s)', async (status) => {
      const { result } = await run(api.get(), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a status that does not exist', { ...CONNECTED, status: 'broken' }],
      ['a missing athlete id', { ...CONNECTED, athlete_id: undefined }],
      ['a timestamp that is not text', { ...CONNECTED, connected_at: 5 }],
      ['a last_sync_at that is not text or null', { ...CONNECTED, last_sync_at: 5 }],
      ['a missing last_sync_at', { ...CONNECTED, last_sync_at: undefined }],
      [
        'a last_sync_error that is not a known code',
        { ...CONNECTED, last_sync_error: 'raw error' },
      ],
      ['a last_sync_error that is null', { ...CONNECTED, last_sync_error: null }],
      ['an empty object', {}],
      ['no body', null],
    ])('rejects an answer with %s', async (_label, body) => {
      await expect(run(api.get(), 'GET', URL, body, 200)).rejects.toBeDefined();
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.get(), 'GET', URL, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('connect', () => {
    it('sends the key in the body of a PUT and nowhere else', async () => {
      const { request } = await run(api.connect(KEY), 'PUT', URL, CONNECTED, 200);

      expect(request.request.body).toEqual({ api_key: KEY });
      expect(request.request.url).not.toContain(KEY);
      expect(request.request.urlWithParams).not.toContain(KEY);
      expect(request.request.headers.keys()).not.toContain('authorization');
    });

    it('returns the connection without the key', async () => {
      const { result } = await run(
        api.connect(KEY),
        'PUT',
        URL,
        { ...CONNECTED, api_key: KEY },
        200,
      );

      expect(result).toEqual({ kind: 'connected', connection: CONNECTION });
      expect(JSON.stringify(result)).not.toContain(KEY);
    });

    it('returns the messages when the key is not accepted', async () => {
      const message = 'Intervals.icu did not accept this API key. Check that you copied all of it.';

      const { result } = await run(api.connect(KEY), 'PUT', URL, { api_key: [message] }, 400);

      expect(result).toEqual({ kind: 'invalid_key', errors: [message] });
    });

    it('collects all messages', async () => {
      const { result } = await run(
        api.connect(KEY),
        'PUT',
        URL,
        { api_key: ['One.', 'Two.'], other: ['Three.'] },
        400,
      );

      expect(result).toEqual({ kind: 'invalid_key', errors: ['One.', 'Two.', 'Three.'] });
    });

    it.each([{}, 'bad request', { api_key: [] }, { detail: 5 }])(
      'falls back to a generic message for the 400 body %j',
      async (body) => {
        const { result } = await run(api.connect(KEY), 'PUT', URL, body, 400);

        expect(result).toEqual({ kind: 'invalid_key', errors: ['The key was not accepted.'] });
      },
    );

    it('shows the text of a plain error message, too', async () => {
      const { result } = await run(
        api.connect(KEY),
        'PUT',
        URL,
        { detail: 'JSON parse error' },
        400,
      );

      expect(result).toEqual({ kind: 'invalid_key', errors: ['JSON parse error'] });
    });

    it('reports too many tries', async () => {
      const { result } = await run(api.connect(KEY), 'PUT', URL, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([
      [503, UNAVAILABLE],
      [502, ODD_ANSWER],
    ])(
      'reports Intervals.icu as unavailable on %s with the message of the server',
      async (status, body) => {
        const { result } = await run(api.connect(KEY), 'PUT', URL, body, status);

        expect(result).toEqual({ kind: 'unavailable', message: body.detail });
      },
    );

    it.each([{}, 'text', { detail: '' }, { detail: 5 }])(
      'uses a standard message when the 503 body has no usable detail (%j)',
      async (body) => {
        const { result } = await run(api.connect(KEY), 'PUT', URL, body, 503);

        expect(result).toEqual({
          kind: 'unavailable',
          message: 'Intervals.icu cannot be reached right now. Please try again later.',
        });
      },
    );

    it.each([401, 403])('reports a lost session (%s)', async (status) => {
      const { result } = await run(api.connect(KEY), 'PUT', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.connect(KEY), 'PUT', URL, 'boom', 500)).rejects.toBeDefined();
    });

    it('rejects when the answer has no connection in it', async () => {
      await expect(
        run(api.connect(KEY), 'PUT', URL, { connected: false }, 200),
      ).rejects.toBeDefined();
    });
  });

  describe('check', () => {
    it('posts to the check address and returns the connection', async () => {
      const { result, request } = await run(api.check(), 'POST', CHECK, CONNECTED, 200);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'checked', connection: CONNECTION });
    });

    it('returns an invalid connection as a result, not as an error', async () => {
      const { result } = await run(
        api.check(),
        'POST',
        CHECK,
        { ...CONNECTED, status: 'invalid' },
        200,
      );

      expect(result).toEqual({
        kind: 'checked',
        connection: { ...CONNECTION, status: 'invalid' },
      });
    });

    it('says when there is nothing to check', async () => {
      const { result } = await run(api.check(), 'POST', CHECK, { detail: 'Not connected.' }, 404);

      expect(result).toEqual({ kind: 'not_connected' });
    });

    it('reports too many tries', async () => {
      const { result } = await run(api.check(), 'POST', CHECK, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('reports Intervals.icu as unavailable', async () => {
      const { result } = await run(api.check(), 'POST', CHECK, UNAVAILABLE, 503);

      expect(result).toEqual({ kind: 'unavailable', message: UNAVAILABLE.detail });
    });

    it.each([401, 403])('reports a lost session (%s)', async (status) => {
      const { result } = await run(api.check(), 'POST', CHECK, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.check(), 'POST', CHECK, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('disconnect', () => {
    it('sends a DELETE and reports the removal', async () => {
      const { result, request } = await run(api.disconnect(), 'DELETE', URL, null, 204);

      expect(request.request.method).toBe('DELETE');
      expect(result).toEqual({ kind: 'disconnected' });
    });

    it.each([401, 403])('reports a lost session (%s)', async (status) => {
      const { result } = await run(api.disconnect(), 'DELETE', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.disconnect(), 'DELETE', URL, 'boom', 500)).rejects.toBeDefined();
    });
  });
});
