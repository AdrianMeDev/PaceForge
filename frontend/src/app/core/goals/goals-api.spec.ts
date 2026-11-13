import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { GoalsApi } from './goals-api';
import { Goal, GoalInput } from './goals-models';

const URL = '/api/goals/';
const ID = '01a1d513-b0b8-74f0-a24c-4a49d0c1531d';

// The shape is that of the real API (replayed with curl against a real Django).
const RACE = {
  id: ID,
  kind: 'race',
  title: 'Berlin Marathon',
  notes: '',
  priority: 'main',
  status: 'active',
  target_date: '2027-09-26',
  discipline: 'running',
  distance_m: 42195.0,
  target_time_seconds: 13500,
  metric: null,
  target_value: null,
  days_to_go: 317,
  created_at: '2026-11-13T13:23:19.864351Z',
  updated_at: '2026-11-13T13:23:19.864357Z',
};
const THRESHOLD = {
  ...RACE,
  id: '01a1d513-b0cc-7123-be4a-47aee16063ff',
  kind: 'threshold',
  title: 'Raise FTP',
  priority: 'secondary',
  target_date: '2027-03-01',
  discipline: null,
  distance_m: null,
  target_time_seconds: null,
  metric: 'ftp',
  target_value: 280,
  days_to_go: 108,
};
const GENERAL = {
  ...THRESHOLD,
  id: '01a1d513-b0e0-7315-9404-55283f44bb38',
  kind: 'general',
  title: 'Build endurance',
  target_date: null,
  metric: null,
  target_value: null,
  days_to_go: null,
};

const NO_SESSION = { detail: 'Authentication credentials were not provided.' };

const REMOVE = Symbol('remove');
type Edit = [path: (string | number)[], value: unknown];

/** A copy of the real answer with places changed or removed, for the answers of the wrong shape. */
function altered(source: object, ...edits: Edit[]): unknown {
  const copy = structuredClone(source) as unknown;
  for (const [path, value] of edits) {
    const parent = path
      .slice(0, -1)
      .reduce<unknown>((node, key) => (node as Record<string | number, unknown>)[key], copy);
    const last = path[path.length - 1];
    if (value === REMOVE) {
      delete (parent as Record<string | number, unknown>)[last];
    } else {
      (parent as Record<string | number, unknown>)[last] = value;
    }
  }
  return copy;
}

describe('GoalsApi', () => {
  let api: GoalsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(GoalsApi);
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

  const WRONG_SHAPES: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'goal'],
    ['no id', altered(RACE, [['id'], REMOVE])],
    ['a number as id', altered(RACE, [['id'], 5])],
    ['an unknown kind', altered(RACE, [['kind'], 'dream'])],
    ['no title', altered(RACE, [['title'], REMOVE])],
    ['no notes', altered(RACE, [['notes'], REMOVE])],
    ['an unknown priority', altered(RACE, [['priority'], 'urgent'])],
    ['an unknown status', altered(RACE, [['status'], 'paused'])],
    ['a date that is no date', altered(RACE, [['target_date'], 'soon'])],
    ['a date with a time', altered(RACE, [['target_date'], '2027-09-26T10:00:00Z'])],
    ['a number as date', altered(RACE, [['target_date'], 20270926])],
    ['an unknown discipline', altered(RACE, [['discipline'], 'rowing'])],
    ['a text as distance', altered(RACE, [['distance_m'], '42195'])],
    ['infinity as distance', altered(RACE, [['distance_m'], Infinity])],
    ['a text as target time', altered(RACE, [['target_time_seconds'], '13500'])],
    ['an unknown metric', altered(THRESHOLD, [['metric'], 'lthr'])],
    ['a text as target value', altered(THRESHOLD, [['target_value'], '280'])],
    ['a fraction as days to go', altered(RACE, [['days_to_go'], 1.5])],
    ['a text as days to go', altered(RACE, [['days_to_go'], 'many'])],
    ['no creation time', altered(RACE, [['created_at'], REMOVE])],
    ['a number as change time', altered(RACE, [['updated_at'], 5])],
  ];

  describe('list', () => {
    it('returns the goals in the order sent', async () => {
      const { result, request } = await run(
        api.list(),
        'GET',
        URL,
        [RACE, THRESHOLD, GENERAL],
        200,
      );

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', goals: [RACE, THRESHOLD, GENERAL] as Goal[] });
    });

    it('returns an empty list', async () => {
      const { result } = await run(api.list(), 'GET', URL, [], 200);

      expect(result).toEqual({ kind: 'ok', goals: [] });
    });

    it('keeps values that do not apply to a kind as null', async () => {
      const bare = altered(GENERAL, [['discipline'], REMOVE], [['distance_m'], REMOVE]);

      const { result } = await run(api.list(), 'GET', URL, [bare], 200);

      expect(result).toMatchObject({
        goals: [{ discipline: null, distance_m: null, metric: null, target_date: null }],
      });
    });

    it('takes over only the known fields', async () => {
      const crowded = altered(RACE, [['owner'], 'x'], [['internal'], { secret: 1 }]);

      const { result } = await run(api.list(), 'GET', URL, [crowded], 200);

      expect(result).toEqual({ kind: 'ok', goals: [RACE] });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.list(), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_SHAPES.slice(3))('rejects a list holding an item with %s', async (_name, bad) => {
      await runFailing(api.list(), 'GET', URL, [RACE, bad] as object[], 200);
    });

    it.each([
      ['no body', null],
      ['a text', 'goals'],
    ])('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.list(), 'GET', URL, bad, 200);
    });

    it.each([null, 5, 'goal', []])('rejects a list holding %j instead of a goal', async (item) => {
      await runFailing(api.list(), 'GET', URL, [item] as object[], 200);
    });

    it('rejects an object instead of a list', async () => {
      await runFailing(api.list(), 'GET', URL, RACE, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.list(), 'GET', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.list();
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === URL));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('create', () => {
    const INPUT: GoalInput = {
      kind: 'race',
      title: 'Berlin Marathon',
      target_date: '2027-09-26',
      discipline: 'running',
      distance_m: 42195,
      target_time_seconds: 13500,
      priority: 'main',
    };

    it('posts the input as it is and returns the goal', async () => {
      const { result, request } = await run(api.create(INPUT), 'POST', URL, RACE, 201);

      expect(request.request.body).toEqual(INPUT);
      expect(result).toEqual({ kind: 'ok', goal: RACE as Goal });
    });

    it('sends nulls where the user cleared a value', async () => {
      const input: GoalInput = { kind: 'race', title: 'x', target_time_seconds: null };

      const { request } = await run(api.create(input), 'POST', URL, RACE, 201);

      expect(request.request.body).toEqual({ kind: 'race', title: 'x', target_time_seconds: null });
    });

    it('returns the messages by field and as one list', async () => {
      const { result } = await run(
        api.create(INPUT),
        'POST',
        URL,
        {
          target_date: ['An active race cannot lie in the past.'],
          priority: ['You already have a main goal. Change it first.'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          'An active race cannot lie in the past.',
          'You already have a main goal. Change it first.',
        ],
        fields: {
          target_date: ['An active race cannot lie in the past.'],
          priority: ['You already have a main goal. Change it first.'],
        },
      });
    });

    it('keeps the messages that concern the whole goal under non_field_errors', async () => {
      const { result } = await run(
        api.create(INPUT),
        'POST',
        URL,
        { non_field_errors: ['You can have at most 30 goals. Delete one first.'] },
        400,
      );

      expect(result).toMatchObject({
        errors: ['You can have at most 30 goals. Delete one first.'],
        fields: { non_field_errors: ['You can have at most 30 goals. Delete one first.'] },
      });
    });

    it('collects several messages of one field and a plain detail text', async () => {
      const { result } = await run(
        api.create(INPUT),
        'POST',
        URL,
        { title: ['a', 'b'], detail: 'JSON parse error' },
        400,
      );

      expect(result).toMatchObject({
        errors: ['a', 'b', 'JSON parse error'],
        fields: { title: ['a', 'b'], detail: ['JSON parse error'] },
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
      ['a list', ['x']],
      ['messages that are no text', { title: [5, null] }],
    ])('uses a fixed message for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.create(INPUT), 'POST', URL, reply, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.create(INPUT), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_SHAPES)('rejects a created answer with %s', async (_name, bad) => {
      await runFailing(api.create(INPUT), 'POST', URL, bad as object | null, 201);
    });

    it.each([200, 404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.create(INPUT), 'POST', URL, 'oops', status);
    });
  });

  describe('update', () => {
    const ADDRESS = `${URL}${ID}/`;

    it('patches only the fields given and returns the goal', async () => {
      const { result, request } = await run(
        api.update(ID, { status: 'achieved' }),
        'PATCH',
        ADDRESS,
        { ...RACE, status: 'achieved' },
        200,
      );

      expect(request.request.body).toEqual({ status: 'achieved' });
      expect(result).toMatchObject({ kind: 'ok', goal: { id: ID, status: 'achieved' } });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(
        api.update('a/b?c', { title: 'x' }),
        'PATCH',
        `${URL}a%2Fb%3Fc/`,
        {},
        404,
      );

      expect(request.request.url).toBe(`${URL}a%2Fb%3Fc/`);
    });

    it('returns the messages when the change is refused', async () => {
      const { result } = await run(
        api.update(ID, { priority: 'main' }),
        'PATCH',
        ADDRESS,
        { priority: ['You already have a main goal. Change it first.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['You already have a main goal. Change it first.'],
        fields: { priority: ['You already have a main goal. Change it first.'] },
      });
    });

    it('says when the goal does not exist or belongs to someone else', async () => {
      const { result } = await run(
        api.update(ID, { title: 'x' }),
        'PATCH',
        ADDRESS,
        { detail: 'No Goal matches the given query.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.update(ID, {}), 'PATCH', ADDRESS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_SHAPES)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.update(ID, {}), 'PATCH', ADDRESS, bad as object | null, 200);
    });

    it.each([201, 405, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.update(ID, {}), 'PATCH', ADDRESS, 'oops', status);
    });
  });

  describe('delete', () => {
    const ADDRESS = `${URL}${ID}/`;

    it('deletes the goal', async () => {
      const { result, request } = await run(api.delete(ID), 'DELETE', ADDRESS, null, 204);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'deleted' });
    });

    it('says when the goal does not exist or belongs to someone else', async () => {
      const { result } = await run(api.delete(ID), 'DELETE', ADDRESS, 'Not found', 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(api.delete('a/b'), 'DELETE', `${URL}a%2Fb/`, null, 404);

      expect(request.request.url).toBe(`${URL}a%2Fb/`);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.delete(ID), 'DELETE', ADDRESS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([200, 400, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.delete(ID), 'DELETE', ADDRESS, 'oops', status);
    });
  });
});
