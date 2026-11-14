import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { ActivitiesApi } from './activities-api';
import { Activity, ActivityDetail, ManualActivityInput } from './activities-models';

const URL = '/api/activities/';
const IMPORT = `${URL}import/`;
const MANUAL = `${URL}manual/`;
const ID = '01a1d3d0-2289-74b2-95b2-17e8712141b0';

// The shapes are those of the real API (replayed with curl against a real Django).
const SUMMARY = {
  id: ID,
  source: 'tcx_file',
  sport: 'running',
  source_sport: 'Running',
  start_time: '2026-10-14T10:33:13Z',
  elapsed_seconds: 3330.0,
  timer_seconds: 3329.0,
  distance_m: 10398.0,
  avg_heart_rate: 145,
  max_heart_rate: 166,
  avg_power_w: null,
  total_ascent_m: null,
  calories: null,
  manufacturer: 'COROS Wearables',
  rpe: null,
  notes: '',
  load: null,
  created_at: '2026-11-13T07:29:55.337064Z',
};
const ACTIVITY: Activity = { ...(SUMMARY as Activity) };
const LAPS = [
  {
    distance_m: 5771.0,
    start_time: '2026-10-14T10:33:13+00:00',
    avg_heart_rate: 141,
    max_heart_rate: 149,
    elapsed_seconds: 1869.0,
  },
  {
    distance_m: null,
    start_time: null,
    avg_heart_rate: null,
    max_heart_rate: null,
    elapsed_seconds: null,
  },
];
const DETAIL: ActivityDetail = { ...ACTIVITY, laps: LAPS };

const NO_SESSION = { detail: 'Authentication credentials were not provided.' };
const THROTTLED = { detail: 'Request was throttled. Expected available in 60 seconds.' };

describe('ActivitiesApi', () => {
  let api: ActivitiesApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ActivitiesApi);
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

  /** The call must fail, and fail with a rejection rather than with a value. */
  async function runFailing(
    action: Promise<unknown>,
    method: string,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    await expect(action).rejects.toThrow();
  }

  const file = () => new File([new Uint8Array([1, 2, 3, 4])], 'run.fit');

  describe('list', () => {
    it('asks for the page and returns it', async () => {
      const { result, request } = await run(
        api.list(50, 100),
        'GET',
        URL,
        { count: 120, next: null, previous: 'http://x/', results: [SUMMARY] },
        200,
      );

      expect(request.request.params.get('limit')).toBe('50');
      expect(request.request.params.get('offset')).toBe('100');
      expect(result).toEqual({ kind: 'ok', page: { count: 120, results: [ACTIVITY] } });
    });

    it('returns an empty page', async () => {
      const { result } = await run(
        api.list(50, 0),
        'GET',
        URL,
        { count: 0, next: null, previous: null, results: [] },
        200,
      );

      expect(result).toEqual({ kind: 'ok', page: { count: 0, results: [] } });
    });

    it('keeps values the file does not report as null', async () => {
      const { result } = await run(
        api.list(50, 0),
        'GET',
        URL,
        { count: 1, results: [{ ...SUMMARY, distance_m: null, avg_heart_rate: undefined }] },
        200,
      );

      expect(result).toMatchObject({
        page: { results: [{ distance_m: null, avg_heart_rate: null }] },
      });
    });

    it('takes over only the known fields', async () => {
      const { result } = await run(
        api.list(50, 0),
        'GET',
        URL,
        { count: 1, results: [{ ...SUMMARY, owner: 7, source_hash: 'abc', gps: [1, 2] }] },
        200,
      );

      expect(result).toEqual({ kind: 'ok', page: { count: 1, results: [ACTIVITY] } });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.list(50, 0), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no count', { results: [] }],
      ['results that are no list', { count: 1, results: {} }],
      ['an unknown sport', { count: 1, results: [{ ...SUMMARY, sport: 'curling' }] }],
      ['an unknown source', { count: 1, results: [{ ...SUMMARY, source: 'gpx_file' }] }],
      ['a text instead of a number', { count: 1, results: [{ ...SUMMARY, distance_m: '10' }] }],
      ['no id', { count: 1, results: [{ ...SUMMARY, id: undefined }] }],
      ['no body', null],
    ])('rejects an answer with %s', async (_name, reply) => {
      await runFailing(api.list(50, 0), 'GET', URL, reply, 200);
    });

    it('rejects a server error', async () => {
      await runFailing(api.list(50, 0), 'GET', URL, 'oops', 500);
    });

    it('rejects when the network fails', async () => {
      const action = api.list(50, 0);
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === URL));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('get', () => {
    it('returns the activity with its laps', async () => {
      const { result } = await run(
        api.get(ID),
        'GET',
        `${URL}${ID}/`,
        { ...SUMMARY, laps: LAPS },
        200,
      );

      expect(result).toEqual({ kind: 'ok', activity: DETAIL });
    });

    it('returns an activity without laps', async () => {
      const { result } = await run(
        api.get(ID),
        'GET',
        `${URL}${ID}/`,
        { ...SUMMARY, laps: [] },
        200,
      );

      expect(result).toEqual({ kind: 'ok', activity: { ...ACTIVITY, laps: [] } });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(api.get('a/b?c'), 'GET', `${URL}a%2Fb%3Fc/`, {}, 404);

      expect(request.request.url).toBe(`${URL}a%2Fb%3Fc/`);
    });

    it('says when the activity is not there or belongs to someone else', async () => {
      const { result } = await run(
        api.get(ID),
        'GET',
        `${URL}${ID}/`,
        '<html>Not found</html>',
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.get(ID), 'GET', `${URL}${ID}/`, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no laps', SUMMARY],
      ['laps that are no list', { ...SUMMARY, laps: 'many' }],
      ['a lap with a text as distance', { ...SUMMARY, laps: [{ ...LAPS[0], distance_m: 'far' }] }],
      ['a lap with a number as start', { ...SUMMARY, laps: [{ ...LAPS[0], start_time: 5 }] }],
    ])('rejects an answer with %s', async (_name, reply) => {
      await runFailing(api.get(ID), 'GET', `${URL}${ID}/`, reply, 200);
    });

    it('rejects a server error', async () => {
      await runFailing(api.get(ID), 'GET', `${URL}${ID}/`, 'oops', 500);
    });
  });

  describe('import', () => {
    it('sends the file as multipart under "file" and returns the activity', async () => {
      const { result, request } = await run(api.import(file()), 'POST', IMPORT, SUMMARY, 201);

      expect(request.request.body).toBeInstanceOf(FormData);
      const sent = (request.request.body as FormData).get('file') as File;
      expect(sent).toBeInstanceOf(File);
      expect(sent.name).toBe('run.fit');
      expect(sent.size).toBe(4);
      expect([...(request.request.body as FormData).keys()]).toEqual(['file']);
      expect(result).toEqual({ kind: 'imported', activity: ACTIVITY });
    });

    it('sets no content type itself, so the browser can add the boundary', async () => {
      const { request } = await run(api.import(file()), 'POST', IMPORT, SUMMARY, 201);

      expect(request.request.headers.has('Content-Type')).toBe(false);
    });

    it('returns the message when the file is rejected', async () => {
      const { result } = await run(
        api.import(file()),
        'POST',
        IMPORT,
        { detail: 'The file is neither a FIT nor a TCX file.' },
        400,
      );

      expect(result).toEqual({
        kind: 'rejected',
        message: 'The file is neither a FIT nor a TCX file.',
      });
    });

    it.each([
      ['no detail', {}],
      ['an empty detail', { detail: '' }],
      ['a detail that is no text', { detail: ['a'] }],
      ['a body that is no object', 'Bad Request'],
    ])('uses a fixed message for a rejection with %s', async (_name, reply) => {
      const { result } = await run(api.import(file()), 'POST', IMPORT, reply, 400);

      expect(result).toEqual({ kind: 'rejected', message: 'The file could not be imported.' });
    });

    it('returns the id of the existing activity for a duplicate', async () => {
      const { result } = await run(
        api.import(file()),
        'POST',
        IMPORT,
        { detail: 'This activity has already been imported.', existing_id: ID },
        409,
      );

      expect(result).toEqual({ kind: 'duplicate', existingId: ID });
    });

    it.each([
      ['no id', { detail: 'x' }],
      ['an empty id', { existing_id: '' }],
      ['an id that is no text', { existing_id: 5 }],
    ])('rejects a duplicate answer with %s', async (_name, reply) => {
      await runFailing(api.import(file()), 'POST', IMPORT, reply, 409);
    });

    it('says when the file is too large, whatever the body looks like', async () => {
      const { result } = await run(
        api.import(file()),
        'POST',
        IMPORT,
        '<html>413 Request Entity Too Large</html>',
        413,
      );

      expect(result).toEqual({ kind: 'too_large' });
    });

    it('says when the user imports too fast', async () => {
      const { result } = await run(api.import(file()), 'POST', IMPORT, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.import(file()), 'POST', IMPORT, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects a created answer of the wrong shape', async () => {
      await runFailing(api.import(file()), 'POST', IMPORT, { id: ID }, 201);
    });

    it.each([415, 500, 502])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.import(file()), 'POST', IMPORT, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.import(file());
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === IMPORT));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('enter', () => {
    const INPUT: ManualActivityInput = {
      sport: 'strength',
      date: '2026-11-12',
      time: '06:30',
      duration_minutes: 45,
      distance_km: null,
      rpe: 7,
      notes: 'Legs were heavy',
    };
    const CREATED = {
      ...SUMMARY,
      source: 'manual',
      sport: 'strength',
      source_sport: '',
      timer_seconds: 2700,
      elapsed_seconds: null,
      distance_m: null,
      rpe: 7,
      notes: 'Legs were heavy',
      load: 315,
    };

    it('posts the form as JSON and returns the activity', async () => {
      const { result, request } = await run(api.enter(INPUT), 'POST', MANUAL, CREATED, 201);

      expect(request.request.body).toEqual(INPUT);
      expect(result).toEqual({
        kind: 'entered',
        activity: expect.objectContaining({
          source: 'manual',
          rpe: 7,
          notes: 'Legs were heavy',
          load: 315,
        }),
      });
    });

    it('reads rpe, note and load of any activity, empty ones as null and empty text', async () => {
      const { result } = await run(
        api.list(20, 0),
        'GET',
        URL,
        {
          count: 1,
          results: [SUMMARY],
        },
        200,
      );

      expect(result).toMatchObject({
        page: { results: [{ rpe: null, notes: '', load: null }] },
      });
    });

    it('returns the messages by field and drops everything else', async () => {
      const { result } = await run(
        api.enter(INPUT),
        'POST',
        MANUAL,
        {
          duration_minutes: ['Ensure this value is less than or equal to 1440.'],
          rpe: ['A valid integer is required.', 5, ''],
          unknown_field: ['ignored'],
          sport: 'not a list',
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: {
          duration_minutes: ['Ensure this value is less than or equal to 1440.'],
          rpe: ['A valid integer is required.'],
        },
        message: null,
      });
    });

    it.each([
      ['a parse error', { detail: 'JSON parse error' }, 'JSON parse error'],
      ['no detail', {}, 'The session could not be saved. Please check your entries.'],
      [
        'a body that is no object',
        'Bad Request',
        'The session could not be saved. Please check your entries.',
      ],
      [
        'only unknown fields',
        { other: ['x'] },
        'The session could not be saved. Please check your entries.',
      ],
    ])(
      'uses the detail or a fixed message for a refusal with %s',
      async (_name, reply, message) => {
        const { result } = await run(api.enter(INPUT), 'POST', MANUAL, reply, 400);

        expect(result).toEqual({ kind: 'invalid', errors: {}, message });
      },
    );

    it('returns the id of the session the user has already', async () => {
      const { result } = await run(
        api.enter(INPUT),
        'POST',
        MANUAL,
        { detail: 'This activity has already been imported.', existing_id: ID },
        409,
      );

      expect(result).toEqual({ kind: 'duplicate', existingId: ID });
    });

    it.each([
      ['no id', { detail: 'x' }],
      ['an empty id', { existing_id: '' }],
      ['an id that is no text', { existing_id: 5 }],
    ])('rejects a duplicate answer with %s', async (_name, reply) => {
      await runFailing(api.enter(INPUT), 'POST', MANUAL, reply, 409);
    });

    it('says when the user enters too fast', async () => {
      const { result } = await run(api.enter(INPUT), 'POST', MANUAL, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.enter(INPUT), 'POST', MANUAL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no note', { ...CREATED, notes: undefined }],
      ['a note that is no text', { ...CREATED, notes: 5 }],
      ['an rpe that is text', { ...CREATED, rpe: '7' }],
      ['a load that is text', { ...CREATED, load: '315' }],
      ['an unknown source', { ...CREATED, source: 'gpx_file' }],
    ])('rejects a created answer with %s', async (_name, reply) => {
      await runFailing(api.enter(INPUT), 'POST', MANUAL, reply, 201);
    });

    it.each([404, 413, 500, 502])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.enter(INPUT), 'POST', MANUAL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.enter(INPUT);
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === MANUAL));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('delete', () => {
    it('deletes the activity', async () => {
      const { result } = await run(api.delete(ID), 'DELETE', `${URL}${ID}/`, null, 204);

      expect(result).toEqual({ kind: 'deleted' });
    });

    it('says when the activity is not there or belongs to someone else', async () => {
      const { result } = await run(api.delete(ID), 'DELETE', `${URL}${ID}/`, 'Not found', 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.delete(ID), 'DELETE', `${URL}${ID}/`, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(api.delete('a/b'), 'DELETE', `${URL}a%2Fb/`, null, 404);

      expect(request.request.url).toBe(`${URL}a%2Fb/`);
    });

    it.each([200, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.delete(ID), 'DELETE', `${URL}${ID}/`, 'oops', status);
    });
  });
});
