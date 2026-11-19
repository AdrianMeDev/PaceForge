import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { SeasonApi } from './season-api';
import { Season, SeasonPlan } from './season-models';

const URL = '/api/season/';

const RACE = {
  date: '2027-02-28',
  priority: 'main',
  discipline: 'running',
  distance_m: 42195,
  title: 'Berlin Marathon',
};
const SEASON = {
  rolling: false,
  truncated: false,
  main_race: RACE,
  peak_minutes: 300,
  weeks: [
    {
      week_start: '2026-11-16',
      phase: 'base',
      recovery: false,
      target_minutes: 240,
      capacity_minutes: 300,
      races: [],
    },
    {
      week_start: '2026-11-23',
      phase: 'base',
      recovery: true,
      target_minutes: 156,
      capacity_minutes: 300,
      races: [{ ...RACE, priority: 'preparation', discipline: null, distance_m: null }],
    },
    {
      week_start: '2027-02-22',
      phase: 'taper',
      recovery: false,
      target_minutes: 135,
      capacity_minutes: 300,
      races: [RACE],
    },
  ],
};
const ROLLING = { ...SEASON, rolling: true, main_race: null, weeks: [] };
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

describe('SeasonApi', () => {
  let api: SeasonApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(SeasonApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  async function runFailing(
    action: Promise<unknown>,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    await expect(action).rejects.toThrow();
  }

  it('reads the weeks, the races and the peak', async () => {
    const { result, request } = await run(api.get(), SEASON, 200);

    expect(request.request.body).toBeNull();
    expect(result).toEqual({ kind: 'ok', season: SEASON as Season });
  });

  it('reads a rolling skeleton without a main race', async () => {
    const { result } = await run(api.get(), ROLLING, 200);

    expect(result).toMatchObject({ kind: 'ok', season: { rolling: true, main_race: null } });
  });

  it('takes over only the known fields', async () => {
    const crowded = altered(
      SEASON,
      [['owner'], 'x'],
      [['weeks', 0, 'note'], 'secret'],
      [['main_race', 'internal'], 1],
    );

    const { result } = await run(api.get(), crowded as object, 200);

    expect(result).toEqual({ kind: 'ok', season: SEASON as Season });
  });

  it.each([401, 403])('says when the session is gone (%i)', async (status) => {
    const { result } = await run(api.get(), NO_SESSION, status);

    expect(result).toEqual({ kind: 'forbidden' });
  });

  it.each([
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'season'],
    ['no rolling flag', altered(SEASON, [['rolling'], REMOVE])],
    ['a text as rolling flag', altered(SEASON, [['rolling'], 'false'])],
    ['no truncated flag', altered(SEASON, [['truncated'], REMOVE])],
    ['a rolling skeleton with a main race', altered(SEASON, [['rolling'], true])],
    ['no main race without rolling', altered(SEASON, [['main_race'], null])],
    ['a fractional peak', altered(SEASON, [['peak_minutes'], 1.5])],
    ['a negative peak', altered(SEASON, [['peak_minutes'], -1])],
    ['no weeks', altered(SEASON, [['weeks'], REMOVE])],
    ['an object as weeks', altered(SEASON, [['weeks'], {}])],
    ['more than 52 weeks', altered(SEASON, [['weeks'], Array(53).fill(SEASON.weeks[0])])],
    ['a text as week', altered(SEASON, [['weeks'], ['week']])],
    ['a week without a start', altered(SEASON, [['weeks', 0, 'week_start'], REMOVE])],
    ['a start that is no date', altered(SEASON, [['weeks', 0, 'week_start'], 'monday'])],
    ['an unknown phase', altered(SEASON, [['weeks', 0, 'phase'], 'peak'])],
    ['no recovery flag', altered(SEASON, [['weeks', 0, 'recovery'], REMOVE])],
    ['a fractional target', altered(SEASON, [['weeks', 0, 'target_minutes'], 10.5])],
    ['a negative capacity', altered(SEASON, [['weeks', 0, 'capacity_minutes'], -5])],
    ['a target above the capacity', altered(SEASON, [['weeks', 0, 'target_minutes'], 301])],
    ['no races', altered(SEASON, [['weeks', 0, 'races'], REMOVE])],
    ['a text as a race', altered(SEASON, [['weeks', 2, 'races'], ['Berlin']])],
    ['a race without a date', altered(SEASON, [['main_race', 'date'], REMOVE])],
    ['a race date with a time', altered(SEASON, [['main_race', 'date'], '2027-02-28T10:00:00Z'])],
    ['an unknown priority', altered(SEASON, [['main_race', 'priority'], 'urgent'])],
    ['an unknown discipline', altered(SEASON, [['main_race', 'discipline'], 'rowing'])],
    ['no discipline', altered(SEASON, [['main_race', 'discipline'], REMOVE])],
    ['a text as distance', altered(SEASON, [['main_race', 'distance_m'], '42195'])],
    ['a zero distance', altered(SEASON, [['main_race', 'distance_m'], 0])],
    ['no distance', altered(SEASON, [['main_race', 'distance_m'], REMOVE])],
    ['no title', altered(SEASON, [['main_race', 'title'], REMOVE])],
    ['a number as title', altered(SEASON, [['main_race', 'title'], 5])],
  ])('rejects an answer with %s', async (_name, bad) => {
    await runFailing(api.get(), bad as object | null, 200);
  });

  it.each([404, 500])('rejects the unexpected status %i', async (status) => {
    await runFailing(api.get(), 'oops', status);
  });

  it('rejects when the network fails', async () => {
    const action = api.get();
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.error(new ProgressEvent('error'));

    await expect(action).rejects.toThrow();
  });
});

const PLANS_URL = '/api/season/plans/';
const ID = '0195f3a0-0000-7000-8000-000000000001';
const OTHER_ID = '0195f3a0-0000-7000-8000-000000000002';
const STAMP = '2026-11-16T10:00:00.123456Z';

describe('SeasonApi reassessment', () => {
  const url = `${URL}reassessment/`;
  const hint = { confirmed_plan_id: ID, reasons: ['goals_changed'], deviation_weeks: [] };
  const evidence = ['2026-10-26', '2026-11-02', '2026-11-09'];
  const deviation = { ...hint, reasons: ['training_deviation'], deviation_weeks: evidence };
  let api: SeasonApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(SeasonApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function answer(body: string | object | null, status = 200) {
    const action = api.reassessment();
    // Attach before flushing so a rejected parse is always handled.
    action.catch(() => undefined);
    const request = await vi.waitFor(() => backend.expectOne(url));
    expect(request.request.method).toBe('GET');
    expect(request.request.body).toBeNull();
    request.flush(body, { status, statusText: `HTTP ${status}` });
    return action;
  }

  it.each([
    hint,
    { ...hint, reasons: [] },
    { ...hint, confirmed_plan_id: null, reasons: [] },
    { ...hint, reasons: ['baseline_unknown'] },
    deviation,
    {
      ...deviation,
      reasons: [
        'goals_changed',
        'ftp_changed',
        'best_times_changed',
        'training_time_changed',
        'training_deviation',
      ],
    },
  ])('reads valid reassessment %j', async (body) => {
    expect(await answer(body)).toEqual({ kind: 'ok', reassessment: body });
  });

  it('takes only the known fields', async () => {
    expect(await answer({ ...hint, owner: 'ignored', message: '<b>ignored</b>' })).toEqual({
      kind: 'ok',
      reassessment: hint,
    });
  });

  it.each([401, 403])('reports session expiry (%i)', async (status) => {
    expect(await answer(NO_SESSION, status)).toEqual({ kind: 'forbidden' });
  });

  it.each([
    ['no body', null],
    ['a text body', 'bad'],
    ['a list body', []],
    ['no id', altered(hint, [['confirmed_plan_id'], REMOVE])],
    ['an invalid id', { ...hint, confirmed_plan_id: '../plans' }],
    ['a numeric id', { ...hint, confirmed_plan_id: 1 }],
    ['reasons without a plan', { ...hint, confirmed_plan_id: null }],
    ['no reasons', altered(hint, [['reasons'], REMOVE])],
    ['a text as reasons', { ...hint, reasons: 'goals_changed' }],
    ['a non-text reason', { ...hint, reasons: [1] }],
    ['an unknown reason', { ...hint, reasons: ['unknown'] }],
    ['a duplicate reason', { ...hint, reasons: ['goals_changed', 'goals_changed'] }],
    ['mixed unknown baseline', { ...hint, reasons: ['baseline_unknown', 'goals_changed'] }],
    ['no evidence field', altered(hint, [['deviation_weeks'], REMOVE])],
    ['null evidence', { ...hint, deviation_weeks: null }],
    ['a text as evidence', { ...hint, deviation_weeks: '2026-11-02' }],
    ['evidence without deviation', { ...hint, deviation_weeks: evidence }],
    ['deviation without evidence', { ...deviation, deviation_weeks: [] }],
    ['two evidence weeks', { ...deviation, deviation_weeks: evidence.slice(0, 2) }],
    ['four evidence weeks', { ...deviation, deviation_weeks: [...evidence, '2026-11-16'] }],
    ['a non-text week', { ...deviation, deviation_weeks: [1, ...evidence.slice(1)] }],
    ['an invalid date', { ...deviation, deviation_weeks: ['2026-02-30', ...evidence.slice(1)] }],
    [
      'an impossible month',
      { ...deviation, deviation_weeks: ['2026-13-01', ...evidence.slice(1)] },
    ],
    [
      'a date with a time',
      { ...deviation, deviation_weeks: ['2026-10-26T00:00:00Z', ...evidence.slice(1)] },
    ],
    ['a Tuesday', { ...deviation, deviation_weeks: ['2026-10-27', ...evidence.slice(1)] }],
    ['duplicate weeks', { ...deviation, deviation_weeks: [evidence[0], evidence[0], evidence[2]] }],
    ['reversed weeks', { ...deviation, deviation_weeks: [...evidence].reverse() }],
    [
      'nonconsecutive weeks',
      { ...deviation, deviation_weeks: ['2026-10-19', ...evidence.slice(1)] },
    ],
  ])('rejects %s', async (_name, body) => {
    await expect(answer(body as object | null)).rejects.toThrow();
  });

  it.each([404, 409, 429, 500, 503])(
    'rejects unavailable or unexpected HTTP %i',
    async (status) => {
      await expect(answer('unavailable', status)).rejects.toThrow();
    },
  );

  it('rejects a network failure', async () => {
    const action = api.reassessment();
    action.catch(() => undefined);
    const request = await vi.waitFor(() => backend.expectOne(url));
    request.error(new ProgressEvent('error'));
    await expect(action).rejects.toThrow();
  });
});

const SUMMARY = {
  id: ID,
  version: 2,
  status: 'confirmed',
  reason: 'Drafted by the coach',
  week_count: 3,
  created_at: STAMP,
  confirmed_at: STAMP,
};
const LIST = {
  plans: [
    SUMMARY,
    { ...SUMMARY, id: OTHER_ID, version: 1, status: 'superseded' },
    {
      ...SUMMARY,
      id: '0195f3a0-0000-7000-8000-000000000003',
      version: 3,
      status: 'draft',
      confirmed_at: null,
    },
  ],
};
const PLAN_WEEKS = SEASON.weeks.map((week, index) => ({
  week_start: week.week_start,
  minutes: index === 2 ? { running: 90 } : { running: 120, cycling: 60 },
  total_minutes: index === 2 ? 90 : 180,
  planned_load: index === 2 ? { running: 123 } : { running: 110, cycling: 55 },
  total_planned_load: index === 2 ? 123 : 165,
  focus: index === 2 ? 'race_specific' : 'endurance',
  key_sessions:
    index === 2
      ? [{ sport: 'running', kind: 'race', minutes: 60, detail: '' }]
      : [{ sport: 'running', kind: 'long', minutes: 90, detail: '3 x 10 min at tempo' }],
  reason: 'Build the base.',
  done: null,
  done_load: null,
}));
const PLAN = {
  id: ID,
  version: 2,
  status: 'confirmed',
  reason: 'Drafted by the coach',
  request: '',
  rationale: 'Base first, then the race.',
  parent: OTHER_ID,
  created_at: STAMP,
  confirmed_at: STAMP,
  skeleton: SEASON,
  weeks: PLAN_WEEKS,
  report: null,
};
const DRAFT = {
  ...PLAN,
  status: 'draft',
  parent: null,
  confirmed_at: null,
  report: {
    valid: false,
    findings: [
      {
        severity: 'error',
        code: 'minutes_outside_target',
        message: 'The week has 10 minutes; the skeleton aims for 240.',
        path: 'weeks[0].minutes',
      },
    ],
  },
};

describe('SeasonApi season plans', () => {
  let api: SeasonApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(SeasonApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function answer(
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<TestRequest> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return request;
  }

  async function failing(
    action: Promise<unknown>,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    await answer(url, reply, status);
    await expect(action).rejects.toThrow();
  }

  describe('plans', () => {
    it('reads the versions in the order of the server', async () => {
      const action = api.plans();
      const request = await answer(PLANS_URL, LIST, 200);

      expect(request.request.body).toBeNull();
      expect(await action).toEqual({ kind: 'ok', plans: LIST.plans });
    });

    it('reads an empty list', async () => {
      const action = api.plans();
      await answer(PLANS_URL, { plans: [] }, 200);

      expect(await action).toEqual({ kind: 'ok', plans: [] });
    });

    it('takes over only the known fields', async () => {
      const action = api.plans();
      await answer(
        PLANS_URL,
        altered(LIST, [['plans', 0, 'owner'], 'x'], [['extra'], 1]) as object,
        200,
      );

      expect(await action).toEqual({ kind: 'ok', plans: LIST.plans });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const action = api.plans();
      await answer(PLANS_URL, NO_SESSION, status);

      expect(await action).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no body', null],
      ['a list as body', []],
      ['no plans', {}],
      ['an object as plans', { plans: {} }],
      ['a text as a plan', { plans: ['x'] }],
      ['no id', altered(LIST, [['plans', 0, 'id'], REMOVE])],
      ['an id that is no uuid', altered(LIST, [['plans', 0, 'id'], '1'])],
      ['version 0', altered(LIST, [['plans', 0, 'version'], 0])],
      ['a fractional version', altered(LIST, [['plans', 0, 'version'], 1.5])],
      ['an unknown status', altered(LIST, [['plans', 0, 'status'], 'live'])],
      ['no reason', altered(LIST, [['plans', 0, 'reason'], REMOVE])],
      ['a negative week count', altered(LIST, [['plans', 0, 'week_count'], -1])],
      ['more than 52 weeks', altered(LIST, [['plans', 0, 'week_count'], 53])],
      ['a time that is no time', altered(LIST, [['plans', 0, 'created_at'], 'yesterday'])],
      ['a confirmed plan without the time', altered(LIST, [['plans', 0, 'confirmed_at'], null])],
      ['a draft with a time of confirming', altered(LIST, [['plans', 2, 'confirmed_at'], STAMP])],
    ])('rejects an answer with %s', async (_name, bad) => {
      await failing(api.plans(), PLANS_URL, bad as object | null, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await failing(api.plans(), PLANS_URL, 'oops', status);
    });
  });

  describe('plan', () => {
    const url = `${PLANS_URL}${ID}/`;

    it('reads a confirmed plan with its weeks and its own skeleton', async () => {
      const action = api.plan(ID);
      const request = await answer(url, PLAN, 200);

      expect(request.request.body).toBeNull();
      expect(await action).toEqual({ kind: 'ok', plan: PLAN as SeasonPlan });
    });

    it('reads a draft with its report', async () => {
      const action = api.plan(ID);
      await answer(url, DRAFT, 200);

      expect(await action).toMatchObject({
        kind: 'ok',
        plan: {
          status: 'draft',
          report: { valid: false, findings: [{ code: 'minutes_outside_target' }] },
        },
      });
    });

    it('reads a week without a key session and a sport left out', async () => {
      const bare = altered(
        PLAN,
        [['weeks', 0, 'key_sessions'], []],
        [['weeks', 0, 'minutes'], { running: 60 }],
        [['weeks', 0, 'total_minutes'], 60],
      );
      const action = api.plan(ID);
      await answer(url, bare as object, 200);

      expect(await action).toMatchObject({
        plan: { weeks: [{ minutes: { running: 60 }, key_sessions: [] }, {}, {}] },
      });
    });

    it('reads minutes and load done of a begun week, an empty week and an unknown week', async () => {
      const done = altered(
        PLAN,
        [
          ['weeks', 0, 'done'],
          [
            { sport: 'running', minutes: 60 },
            { sport: 'other', minutes: 10 },
          ],
        ],
        [['weeks', 1, 'done'], []],
        [
          ['weeks', 0, 'done_load'],
          [
            { sport: 'running', load: 50 },
            { sport: 'other', load: 12 },
          ],
        ],
        [['weeks', 1, 'done_load'], []],
      );
      const action = api.plan(ID);
      await answer(url, done as object, 200);

      expect(await action).toMatchObject({
        plan: {
          weeks: [
            {
              done: [
                { sport: 'running', minutes: 60 },
                { sport: 'other', minutes: 10 },
              ],
              done_load: [
                { sport: 'running', load: 50 },
                { sport: 'other', load: 12 },
              ],
            },
            { done: [], done_load: [] },
            { done: null, done_load: null },
          ],
        },
      });
    });

    it('reads the request a version was made from, as it is', async () => {
      const text = '<img src=x onerror=alert(1)>\nless cycling';
      const action = api.plan(ID);
      await answer(url, altered(PLAN, [['request'], text]) as object, 200);

      expect(await action).toMatchObject({ plan: { request: text } });
    });

    it('reads zero planned load and confirmed workout load in sports absent from season minutes', async () => {
      const action = api.plan(ID);
      await answer(
        url,
        altered(
          PLAN,
          [['weeks', 0, 'planned_load'], {}],
          [['weeks', 0, 'total_planned_load'], 0],
          [['weeks', 1, 'planned_load'], { swimming: 55, strength: 0 }],
          [['weeks', 1, 'total_planned_load'], 55],
        ) as object,
        200,
      );
      expect(await action).toMatchObject({
        plan: {
          weeks: [
            { planned_load: {}, total_planned_load: 0 },
            { planned_load: { swimming: 55, strength: 0 }, total_planned_load: 55 },
            {},
          ],
        },
      });
    });

    it('takes a request of 500 characters, counted as the server counts them', async () => {
      const action = api.plan(ID);
      await answer(url, altered(PLAN, [['request'], '\u{1F600}'.repeat(500)]) as object, 200);

      expect(await action).toMatchObject({ kind: 'ok' });
    });

    it('takes over only the known fields', async () => {
      const crowded = altered(
        PLAN,
        [['owner'], 'x'],
        [['weeks', 0, 'note'], 'secret'],
        [['weeks', 0, 'key_sessions', 0, 'internal'], 1],
      );
      const action = api.plan(ID);
      await answer(url, crowded as object, 200);

      expect(await action).toEqual({ kind: 'ok', plan: PLAN as SeasonPlan });
    });

    it('keeps the texts of the coach as they are, markup included', async () => {
      const text = '<img src=x onerror=alert(1)>';
      const action = api.plan(ID);
      await answer(
        url,
        altered(PLAN, [['rationale'], text], [['weeks', 0, 'reason'], text]) as object,
        200,
      );

      expect(await action).toMatchObject({
        plan: { rationale: text, weeks: [{ reason: text }, {}, {}] },
      });
    });

    it.each(['1', 'not-an-id', '../season', `${ID}/confirm`, ''])(
      'does not ask for %j, which is no id',
      async (id) => {
        expect(await api.plan(id)).toEqual({ kind: 'not_found' });
        backend.expectNone(() => true);
      },
    );

    it('says that a plan does not exist', async () => {
      const action = api.plan(ID);
      await answer(url, { detail: 'There is no such season plan.', code: 'not_found' }, 404);

      expect(await action).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const action = api.plan(ID);
      await answer(url, NO_SESSION, status);

      expect(await action).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no body', null],
      ['a list as body', []],
      ['another id', altered(PLAN, [['id'], 'x'])],
      ['version 0', altered(PLAN, [['version'], 0])],
      ['an unknown status', altered(PLAN, [['status'], 'live'])],
      ['no reason', altered(PLAN, [['reason'], REMOVE])],
      ['no rationale', altered(PLAN, [['rationale'], REMOVE])],
      ['a parent that is no uuid', altered(PLAN, [['parent'], 'x'])],
      ['no parent', altered(PLAN, [['parent'], REMOVE])],
      ['a confirmed plan without the time', altered(PLAN, [['confirmed_at'], null])],
      ['a draft without a report', altered(DRAFT, [['report'], null])],
      ['a confirmed plan with a report', altered(PLAN, [['report'], DRAFT.report])],
      ['a report that contradicts itself', altered(DRAFT, [['report', 'valid'], true])],
      ['no skeleton', altered(PLAN, [['skeleton'], REMOVE])],
      ['a broken skeleton', altered(PLAN, [['skeleton', 'weeks', 0, 'phase'], 'x'])],
      ['no weeks', altered(PLAN, [['weeks'], REMOVE])],
      ['fewer weeks than the skeleton', altered(PLAN, [['weeks'], PLAN_WEEKS.slice(0, 2)])],
      ['weeks in another order', altered(PLAN, [['weeks'], [...PLAN_WEEKS].reverse()])],
      ['a week that is no date', altered(PLAN, [['weeks', 0, 'week_start'], 'monday'])],
      ['an unknown focus', altered(PLAN, [['weeks', 0, 'focus'], 'rest'])],
      ['no reason of a week', altered(PLAN, [['weeks', 0, 'reason'], REMOVE])],
      ['no minutes', altered(PLAN, [['weeks', 0, 'minutes'], REMOVE])],
      ['a list as minutes', altered(PLAN, [['weeks', 0, 'minutes'], []])],
      ['an unknown sport in the minutes', altered(PLAN, [['weeks', 0, 'minutes', 'rowing'], 30])],
      ['fractional minutes', altered(PLAN, [['weeks', 0, 'minutes', 'running'], 10.5])],
      ['negative minutes', altered(PLAN, [['weeks', 0, 'minutes', 'running'], -1])],
      ['a total that is not the sum', altered(PLAN, [['weeks', 0, 'total_minutes'], 181])],
      ['a total above a week', altered(PLAN, [['weeks', 0, 'total_minutes'], 10081])],
      ['no done', altered(PLAN, [['weeks', 0, 'done'], REMOVE])],
      ['no planned load', altered(PLAN, [['weeks', 0, 'planned_load'], REMOVE])],
      ['a list as planned load', altered(PLAN, [['weeks', 0, 'planned_load'], []])],
      ['an unknown load sport', altered(PLAN, [['weeks', 0, 'planned_load', 'other'], 5])],
      ['negative planned load', altered(PLAN, [['weeks', 0, 'planned_load', 'running'], -1])],
      ['fractional planned load', altered(PLAN, [['weeks', 0, 'planned_load', 'running'], 1.5])],
      ['no load total', altered(PLAN, [['weeks', 0, 'total_planned_load'], REMOVE])],
      ['a negative load total', altered(PLAN, [['weeks', 0, 'total_planned_load'], -1])],
      ['a fractional load total', altered(PLAN, [['weeks', 0, 'total_planned_load'], 165.5])],
      [
        'a load total that is not the sum',
        altered(PLAN, [['weeks', 0, 'total_planned_load'], 166]),
      ],
      ['no done load', altered(PLAN, [['weeks', 0, 'done_load'], REMOVE])],
      ['a text as done load', altered(PLAN, [['weeks', 0, 'done_load'], 'none'])],
      ['an object as done load', altered(PLAN, [['weeks', 0, 'done_load'], {}])],
      ['a text as done load entry', altered(PLAN, [['weeks', 0, 'done_load'], ['running']])],
      [
        'an unknown done load sport',
        altered(PLAN, [['weeks', 0, 'done_load'], [{ sport: 'rowing', load: 5 }]]),
      ],
      [
        'duplicate done load sport',
        altered(PLAN, [
          ['weeks', 0, 'done_load'],
          [
            { sport: 'running', load: 5 },
            { sport: 'running', load: 6 },
          ],
        ]),
      ],
      [
        'fractional done load',
        altered(PLAN, [['weeks', 0, 'done_load'], [{ sport: 'running', load: 1.5 }]]),
      ],
      [
        'negative done load',
        altered(PLAN, [['weeks', 0, 'done_load'], [{ sport: 'running', load: -1 }]]),
      ],
      [
        'zero done load',
        altered(PLAN, [['weeks', 0, 'done_load'], [{ sport: 'running', load: 0 }]]),
      ],
      ['a text as done', altered(PLAN, [['weeks', 0, 'done'], 'none'])],
      ['an object as done', altered(PLAN, [['weeks', 0, 'done'], {}])],
      ['a text as a done entry', altered(PLAN, [['weeks', 0, 'done'], ['running']])],
      [
        'an unknown sport done',
        altered(PLAN, [['weeks', 0, 'done'], [{ sport: 'rowing', minutes: 5 }]]),
      ],
      [
        'a sport done twice',
        altered(PLAN, [
          ['weeks', 0, 'done'],
          [
            { sport: 'running', minutes: 5 },
            { sport: 'running', minutes: 6 },
          ],
        ]),
      ],
      [
        'fractional minutes done',
        altered(PLAN, [['weeks', 0, 'done'], [{ sport: 'running', minutes: 1.5 }]]),
      ],
      [
        'no minutes done',
        altered(PLAN, [['weeks', 0, 'done'], [{ sport: 'running', minutes: 0 }]]),
      ],
      ['no request', altered(PLAN, [['request'], REMOVE])],
      ['a number as request', altered(PLAN, [['request'], 5])],
      ['a request of 501 characters', altered(PLAN, [['request'], 'x'.repeat(501)])],
      ['no key sessions', altered(PLAN, [['weeks', 0, 'key_sessions'], REMOVE])],
      [
        'four key sessions',
        altered(PLAN, [['weeks', 0, 'key_sessions'], Array(4).fill(PLAN_WEEKS[0].key_sessions[0])]),
      ],
      ['a text as key session', altered(PLAN, [['weeks', 0, 'key_sessions'], ['long']])],
      [
        'an unknown sport of a session',
        altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'sport'], 'rowing']),
      ],
      ['an unknown kind', altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'kind'], 'party'])],
      ['a session of 0 minutes', altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'minutes'], 0])],
      [
        'a session of more than a day',
        altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'minutes'], 1441]),
      ],
      ['no detail', altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'detail'], REMOVE])],
      [
        'a detail of 61 characters',
        altered(PLAN, [['weeks', 0, 'key_sessions', 0, 'detail'], 'x'.repeat(61)]),
      ],
    ])('rejects an answer with %s', async (_name, bad) => {
      await failing(api.plan(ID), url, bad as object | null, 200);
    });

    it.each([409, 422, 500])('rejects the unexpected status %i', async (status) => {
      await failing(api.plan(ID), url, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.plan(ID);
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne(url));
      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });
});

describe('SeasonApi acting on season plans', () => {
  let api: SeasonApi;
  let backend: HttpTestingController;
  const GENERATE = `${PLANS_URL}generate/`;
  const PROVIDER_TEXT = 'The provider did not accept the key. Check that you copied all of it.';
  const THROTTLED = { detail: 'Request was throttled. Expected available in 60 seconds.' };
  const PROXY_PAGE = '<html><body>Bad gateway</body></html>';

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(SeasonApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function post<T>(
    action: Promise<T>,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'POST' && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  async function postFailing(
    action: Promise<unknown>,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    await post(
      action.catch(() => undefined),
      url,
      reply,
      status,
    );
    await expect(action).rejects.toThrow();
  }

  describe('generate', () => {
    it('posts and returns the draft', async () => {
      const { result, request } = await post(api.generate(), GENERATE, DRAFT, 201);

      expect(request.request.body).toEqual({});
      expect(result).toMatchObject({ kind: 'ok', plan: { status: 'draft', id: ID } });
    });

    it('says when no provider is set up', async () => {
      const { result } = await post(
        api.generate(),
        GENERATE,
        { detail: 'No AI provider is set up.', code: 'not_configured' },
        409,
      );

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when no week of the season offers training time', async () => {
      const { result } = await post(
        api.generate(),
        GENERATE,
        { detail: 'You have no training time.', code: 'no_time' },
        409,
      );

      expect(result).toEqual({ kind: 'no_time' });
    });

    it.each([
      ['no body', null],
      ['a page of a proxy', PROXY_PAGE],
      ['a list as body', []],
      ['an unknown code', { code: 'weird' }],
      ['the code in other letters', { code: 'NO_TIME' }],
    ])('keeps a 409 with %s as "no provider"', async (_name, body) => {
      const { result } = await post(api.generate(), GENERATE, body as object | null, 409);

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when the coach gave nothing usable, and what was wrong', async () => {
      const problems = [{ path: '', message: 'The answer is not one JSON object.' }];

      const { result } = await post(
        api.generate(),
        GENERATE,
        { detail: 'The coach did not give a plan.', code: 'not_usable', problems },
        422,
      );

      expect(result).toEqual({ kind: 'not_usable', problems });
    });

    it.each([
      ['no problems', { code: 'not_usable' }],
      ['an object as problems', { problems: {} }],
      ['a problem without a message', { problems: [{ path: '' }] }],
    ])('rejects an unusable-plan answer with %s', async (_name, body) => {
      await postFailing(api.generate(), GENERATE, body, 422);
    });

    it('says when this server limits the requests', async () => {
      const { result } = await post(api.generate(), GENERATE, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('returns the provider asking to slow down with the time to wait', async () => {
      const { result } = await post(
        api.generate(),
        GENERATE,
        { detail: 'Slow down.', code: 'rate_limited', retry_after: 17 },
        429,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'Slow down.',
        retry_after: 17,
      });
    });

    it.each([
      [502, 'invalid_key'],
      [502, 'unexpected'],
      [502, 'not_allowed'],
      [503, 'unavailable'],
    ])('returns the problem %i %s with the text of the server', async (status, code) => {
      const { result } = await post(
        api.generate(),
        GENERATE,
        { detail: PROVIDER_TEXT, code },
        status,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: code,
        message: PROVIDER_TEXT,
        retry_after: null,
      });
    });

    it.each([
      [502, 'unexpected'],
      [503, 'unavailable'],
    ])(
      'keeps a %i without a code a problem of its own kind, with a fixed text',
      async (status, problem) => {
        const { result } = await post(api.generate(), GENERATE, PROXY_PAGE, status);

        expect(result).toMatchObject({ kind: 'provider_problem', problem });
        expect(JSON.stringify(result)).not.toContain('Bad gateway');
      },
    );

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await post(api.generate(), GENERATE, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a draft without a report', altered(DRAFT, [['report'], null])],
      ['a broken week', altered(DRAFT, [['weeks', 0, 'focus'], 'rest'])],
      ['no body', null],
    ])('rejects a draft with %s', async (_name, bad) => {
      await postFailing(api.generate(), GENERATE, bad as object | null, 201);
    });

    it.each([200, 404, 500])('rejects the unexpected status %i', async (status) => {
      await postFailing(api.generate(), GENERATE, 'oops', status);
    });
  });

  describe.each([
    ['confirm', (id: string) => api.confirm(id)],
    ['discard', (id: string) => api.discard(id)],
  ])('%s', (action, call) => {
    const url = `${PLANS_URL}${ID}/${action}/`;
    const decided =
      action === 'confirm' ? PLAN : { ...PLAN, status: 'discarded', confirmed_at: null };

    it('posts to the address of the plan and returns it', async () => {
      const { result, request } = await post(call(ID), url, decided, 200);

      expect(request.request.body).toEqual({});
      expect(result).toMatchObject({ kind: 'ok', plan: { id: ID, status: decided.status } });
    });

    it('says that a plan does not exist', async () => {
      const { result } = await post(call(ID), url, { code: 'not_found' }, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('says that only a draft can be decided on', async () => {
      const { result } = await post(call(ID), url, { code: 'not_a_draft' }, 409);

      expect(result).toEqual({ kind: 'not_a_draft' });
    });

    it.each(['1', 'not-an-id', '../season', `${ID}/x`])(
      'does not send %j, which is no id',
      async (id) => {
        expect(await call(id)).toEqual({ kind: 'not_found' });
        backend.expectNone(() => true);
      },
    );

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await post(call(ID), url, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects a plan of the wrong shape', async () => {
      await postFailing(call(ID), url, altered(decided, [['weeks'], REMOVE]) as object, 200);
    });

    it.each([429, 500, 502])('rejects the unexpected status %i', async (status) => {
      await postFailing(call(ID), url, 'oops', status);
    });
  });

  describe('confirm with errors', () => {
    const url = `${PLANS_URL}${ID}/confirm/`;
    const findings = DRAFT.report.findings;

    it('returns the findings of a plan that cannot be confirmed', async () => {
      const { result } = await post(
        api.confirm(ID),
        url,
        {
          detail: 'The plan has errors and cannot be confirmed.',
          code: 'not_confirmable',
          findings,
        },
        422,
      );

      expect(result).toEqual({ kind: 'not_confirmable', findings });
    });

    it.each([
      ['no findings', { code: 'not_confirmable' }],
      ['a text as finding', { findings: ['bad'] }],
      ['an unknown severity', { findings: [{ ...findings[0], severity: 'fatal' }] }],
      ['a finding without a message', { findings: [{ severity: 'error', code: 'x', path: '' }] }],
    ])('rejects an answer with %s', async (_name, body) => {
      await postFailing(api.confirm(ID), url, body, 422);
    });
  });

  describe('restore', () => {
    const url = `${PLANS_URL}${ID}/restore/`;
    const restored = { ...DRAFT, parent: ID, reason: 'Restored from version 1' };

    it('posts to the address of the version and returns the new draft', async () => {
      const { result, request } = await post(api.restore(ID), url, restored, 201);

      expect(request.request.body).toEqual({});
      expect(result).toMatchObject({
        kind: 'ok',
        plan: { status: 'draft', parent: ID, reason: 'Restored from version 1' },
      });
    });

    it('says that a version does not exist', async () => {
      const { result } = await post(api.restore(ID), url, { code: 'not_found' }, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('says that only a replaced or discarded version can be restored', async () => {
      const { result } = await post(api.restore(ID), url, { code: 'not_restorable' }, 409);

      expect(result).toEqual({ kind: 'not_restorable' });
    });

    it.each(['1', 'not-an-id', '../season', `${ID}/x`])(
      'does not send %j, which is no id',
      async (id) => {
        expect(await api.restore(id)).toEqual({ kind: 'not_found' });
        backend.expectNone(() => true);
      },
    );

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await post(api.restore(ID), url, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a draft without a report', altered(restored, [['report'], null])],
      ['a broken week', altered(restored, [['weeks', 0, 'focus'], 'rest'])],
      ['no body', null],
    ])('rejects a draft with %s', async (_name, bad) => {
      await postFailing(api.restore(ID), url, bad as object | null, 201);
    });

    it.each([200, 422, 429, 500, 502])('rejects the unexpected status %i', async (status) => {
      await postFailing(api.restore(ID), url, 'oops', status);
    });
  });

  describe('change', () => {
    const url = `${PLANS_URL}${ID}/change/`;
    const changed = { ...DRAFT, parent: ID, request: 'Less cycling in January' };

    it('posts the request and returns the new draft', async () => {
      const { result, request } = await post(
        api.change(ID, 'Less cycling in January'),
        url,
        changed,
        201,
      );

      expect(request.request.body).toEqual({ request: 'Less cycling in January' });
      expect(result).toMatchObject({
        kind: 'ok',
        plan: { status: 'draft', parent: ID, request: 'Less cycling in January' },
      });
    });

    it('returns the messages of a request that was not accepted, by field and as a list', async () => {
      const { result } = await post(
        api.change(ID, ''),
        url,
        { request: ['Say what you want changed.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['Say what you want changed.'],
        fields: { request: ['Say what you want changed.'] },
      });
    });

    it('says that a version does not exist', async () => {
      const { result } = await post(api.change(ID, 'x'), url, { code: 'not_found' }, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('says that only the confirmed version and a draft can be changed', async () => {
      const { result } = await post(api.change(ID, 'x'), url, { code: 'not_changeable' }, 409);

      expect(result).toEqual({ kind: 'not_changeable' });
    });

    it('says when the current season has no training time', async () => {
      const { result } = await post(
        api.change(ID, 'x'),
        url,
        { detail: 'You have no training time.', code: 'no_time' },
        409,
      );

      expect(result).toEqual({ kind: 'no_time' });
    });

    it.each([
      ['the code of the provider', { code: 'not_configured' }],
      ['no body', null],
      ['a page of a proxy', PROXY_PAGE],
      ['an unknown code', { code: 'weird' }],
    ])('keeps a 409 with %s as "no provider"', async (_name, body) => {
      const { result } = await post(api.change(ID, 'x'), url, body as object | null, 409);

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when the coach gave the season back as it was', async () => {
      const { result } = await post(api.change(ID, 'x'), url, { code: 'unchanged' }, 422);

      expect(result).toEqual({ kind: 'unchanged' });
    });

    it('says when the coach gave nothing usable, and what was wrong', async () => {
      const problems = [{ path: '', message: 'The answer is not one JSON object.' }];

      const { result } = await post(
        api.change(ID, 'x'),
        url,
        { code: 'not_usable', problems },
        422,
      );

      expect(result).toEqual({ kind: 'not_usable', problems });
    });

    it('rejects an unusable-plan answer without problems', async () => {
      await postFailing(api.change(ID, 'x'), url, { code: 'not_usable' }, 422);
    });

    it('says when this server limits the requests', async () => {
      const { result } = await post(api.change(ID, 'x'), url, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([
      [502, 'invalid_key'],
      [503, 'unavailable'],
    ])('returns the problem %i %s with the text of the server', async (status, code) => {
      const { result } = await post(
        api.change(ID, 'x'),
        url,
        { detail: PROVIDER_TEXT, code },
        status,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: code,
        message: PROVIDER_TEXT,
        retry_after: null,
      });
    });

    it.each(['1', 'not-an-id', '../season', `${ID}/x`])(
      'does not send %j, which is no id',
      async (id) => {
        expect(await api.change(id, 'x')).toEqual({ kind: 'not_found' });
        backend.expectNone(() => true);
      },
    );

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await post(api.change(ID, 'x'), url, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a draft without a report', altered(changed, [['report'], null])],
      ['a broken week', altered(changed, [['weeks', 0, 'focus'], 'rest'])],
      ['no body', null],
    ])('rejects a draft with %s', async (_name, bad) => {
      await postFailing(api.change(ID, 'x'), url, bad as object | null, 201);
    });

    it.each([200, 500])('rejects the unexpected status %i', async (status) => {
      await postFailing(api.change(ID, 'x'), url, 'oops', status);
    });
  });
});
