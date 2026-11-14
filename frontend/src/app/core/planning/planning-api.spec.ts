import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { PlanningApi } from './planning-api';
import { ListWeeksResult, WeekPlan } from './planning-models';

const WEEKS_URL = '/api/planning/weeks/';
const DRAFT_ID = '01a1d73d-2f26-7356-907e-f1475fc2aeab';
const CONFIRMED_ID = '01a1d73d-6471-72e5-87a1-61b21e8ed49a';
const OTHER_ID = '01a1d73d-0000-7000-8000-000000000000';

// The shapes are those of the real API (replayed with curl against a real Django and a fake
// coach): a draft whose interval workout does not add up, and a confirmed plan.
const DRAFT = {
  id: DRAFT_ID,
  week_start: '2026-11-16',
  version: 1,
  status: 'draft',
  reason: 'Drafted by the coach',
  rationale: 'Base week with one tempo session.',
  parent: null,
  created_at: '2026-11-13T23:27:53.638352Z',
  confirmed_at: null,
  workouts: [
    {
      day: '2026-11-16',
      sport: 'cycling',
      title: 'Endurance ride',
      goal: 'endurance',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 2,
      notes: 'Keep it easy',
      segments: [],
    },
    {
      day: '2026-11-18',
      sport: 'cycling',
      title: 'Tempo ride',
      goal: 'tempo',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 3,
      notes: 'Keep it easy',
      segments: [],
    },
    {
      day: '2026-11-20',
      sport: 'cycling',
      title: 'Intervals',
      goal: 'threshold',
      duration_minutes: 60,
      zone_system: null,
      zone: null,
      notes: 'Keep it easy',
      segments: [
        { kind: 'warmup', seconds: 900, repeat: 1, zone_system: 'power', zone: 2 },
        { kind: 'work', seconds: 600, repeat: 3, zone_system: 'power', zone: 4 },
        { kind: 'recovery', seconds: 300, repeat: 3, zone_system: 'power', zone: 1 },
        { kind: 'cooldown', seconds: 600, repeat: 1, zone_system: 'power', zone: 1 },
      ],
    },
  ],
  report: {
    valid: false,
    findings: [
      {
        severity: 'error',
        code: 'segments_mismatch',
        message: 'The segments add up to 4200 seconds, the workout says 3600 seconds.',
        path: 'workouts[2].segments',
      },
    ],
  },
};
const CONFIRMED = {
  id: CONFIRMED_ID,
  week_start: '2026-11-23',
  version: 1,
  status: 'confirmed',
  reason: 'by hand',
  rationale: 'Easy week',
  parent: null,
  created_at: '2026-11-13T23:28:07.281568Z',
  confirmed_at: '2026-11-13T23:28:07.353166Z',
  workouts: [
    {
      day: '2026-11-23',
      sport: 'cycling',
      title: 'Endurance ride',
      goal: 'endurance',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 2,
      notes: '',
      segments: [],
    },
  ],
  report: null,
};
const DISCARDED = { ...DRAFT, status: 'discarded', report: null };
const VALID_DRAFT = { ...DRAFT, report: { valid: true, findings: [] } };
const WARNED_DRAFT = {
  ...DRAFT,
  report: {
    valid: true,
    findings: [
      {
        severity: 'warning',
        code: 'no_free_day',
        message: 'The week has no day without a workout.',
        path: '',
      },
    ],
  },
};
const SUPERSEDED = { ...CONFIRMED, status: 'superseded' };

const VERSION = {
  id: DRAFT_ID,
  version: 1,
  status: 'discarded',
  reason: 'Drafted by the coach',
  workout_count: 3,
  created_at: '2026-11-13T23:27:53.638352Z',
  confirmed_at: null,
};
const WEEKS = {
  weeks: [
    { week_start: '2026-11-09', plans: [] },
    { week_start: '2026-11-16', plans: [VERSION] },
    { week_start: '2026-11-23', plans: [] },
    { week_start: '2026-11-30', plans: [] },
    { week_start: '2026-12-07', plans: [] },
  ],
};

const NO_SESSION = { detail: 'Authentication credentials were not provided.' };
const THROTTLED = { detail: 'Request was throttled. Expected available in 60 seconds.' };
const NOT_FOUND = { detail: 'There is no such plan.', code: 'not_found' };
const NOT_A_DRAFT = { detail: 'Only a draft can be confirmed or discarded.', code: 'not_a_draft' };
const PROVIDER_TEXT = 'The provider did not accept the key. Check that you copied all of it.';
const PROXY_PAGE = '<html><body>Bad Gateway</body></html>';

/** The first version in the second week of a `weeks()` result. */
function versionOf(result: ListWeeksResult): unknown {
  if (result.kind !== 'ok') {
    throw new Error('Expected a list of weeks');
  }
  return result.weeks[1].plans[0];
}

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

const WORKOUT = ['workouts', 0] as const;
const SEGMENT = ['workouts', 2, 'segments', 0] as const;
const FINDING = ['report', 'findings', 0] as const;

/** Answers that are no plan: each must make a call that returns a plan reject. */
const WRONG_PLANS: [string, unknown][] = [
  ['no body', null],
  ['a list as body', []],
  ['a text as body', 'plan'],
  ['no id', altered(DRAFT, [['id'], REMOVE])],
  ['an id that is no uuid', altered(DRAFT, [['id'], 'x'])],
  ['a number as id', altered(DRAFT, [['id'], 5])],
  ['no week', altered(DRAFT, [['week_start'], REMOVE])],
  ['a week that is no date', altered(DRAFT, [['week_start'], '2026-02-30'])],
  ['a week that is no Monday', altered(DRAFT, [['week_start'], '2026-11-17'])],
  ['a week in another format', altered(DRAFT, [['week_start'], '20261116'])],
  ['version 0', altered(DRAFT, [['version'], 0])],
  ['a text as version', altered(DRAFT, [['version'], '1'])],
  ['a fraction as version', altered(DRAFT, [['version'], 1.5])],
  ['an unknown status', altered(DRAFT, [['status'], 'done'])],
  ['no status', altered(DRAFT, [['status'], REMOVE])],
  ['no reason', altered(DRAFT, [['reason'], REMOVE])],
  ['a number as reason', altered(DRAFT, [['reason'], 5])],
  ['no rationale', altered(DRAFT, [['rationale'], REMOVE])],
  ['a number as rationale', altered(DRAFT, [['rationale'], 5])],
  ['no parent', altered(DRAFT, [['parent'], REMOVE])],
  ['a parent that is no uuid', altered(DRAFT, [['parent'], 'x'])],
  ['a time of creation that is no time', altered(DRAFT, [['created_at'], 'yesterday'])],
  ['no time of creation', altered(DRAFT, [['created_at'], REMOVE])],
  ['a draft that was confirmed', altered(DRAFT, [['confirmed_at'], '2026-11-13T23:28:07Z'])],
  ['a confirmed plan that was never confirmed', altered(CONFIRMED, [['confirmed_at'], null])],
  ['a time of confirming that is no time', altered(CONFIRMED, [['confirmed_at'], 'soon'])],
  ['a replaced plan that was never confirmed', altered(SUPERSEDED, [['confirmed_at'], null])],
  [
    'a discarded plan that was confirmed',
    altered(DISCARDED, [['confirmed_at'], '2026-11-13T23:28:07Z']),
  ],
  ['no workouts', altered(DRAFT, [['workouts'], REMOVE])],
  ['an object as workouts', altered(DRAFT, [['workouts'], {}])],
  ['a text as workout', altered(DRAFT, [['workouts'], ['run']])],
  ['a draft without a report', altered(DRAFT, [['report'], null])],
  ['a draft with a missing report', altered(DRAFT, [['report'], REMOVE])],
  [
    'a confirmed plan with a report',
    altered(CONFIRMED, [['report'], { valid: true, findings: [] }]),
  ],
  [
    'a discarded plan with a report',
    altered(DISCARDED, [['report'], { valid: true, findings: [] }]),
  ],
  ['a text as report', altered(DRAFT, [['report'], 'valid'])],
  ['a text as validity', altered(DRAFT, [['report', 'valid'], 'false'])],
  ['no validity', altered(DRAFT, [['report', 'valid'], REMOVE])],
  ['valid despite an error', altered(DRAFT, [['report', 'valid'], true])],
  ['invalid without an error', altered(WARNED_DRAFT, [['report', 'valid'], false])],
  ['no findings', altered(DRAFT, [['report', 'findings'], REMOVE])],
  ['an object as findings', altered(DRAFT, [['report', 'findings'], {}])],
  ['a text as finding', altered(DRAFT, [['report', 'findings'], ['bad']])],
  ['an unknown severity', altered(DRAFT, [[...FINDING, 'severity'], 'fatal'])],
  ['a number as code', altered(DRAFT, [[...FINDING, 'code'], 5])],
  ['no message', altered(DRAFT, [[...FINDING, 'message'], REMOVE])],
  ['a number as path', altered(DRAFT, [[...FINDING, 'path'], 5])],
  ['a day that is no date', altered(DRAFT, [[...WORKOUT, 'day'], '2026-13-01'])],
  ['no day', altered(DRAFT, [[...WORKOUT, 'day'], REMOVE])],
  ['an unknown sport', altered(DRAFT, [[...WORKOUT, 'sport'], 'skiing'])],
  ['no sport', altered(DRAFT, [[...WORKOUT, 'sport'], REMOVE])],
  ['no title', altered(DRAFT, [[...WORKOUT, 'title'], REMOVE])],
  ['an empty title', altered(DRAFT, [[...WORKOUT, 'title'], ''])],
  ['a number as title', altered(DRAFT, [[...WORKOUT, 'title'], 5])],
  ['an unknown goal', altered(DRAFT, [[...WORKOUT, 'goal'], 'fun'])],
  ['no goal', altered(DRAFT, [[...WORKOUT, 'goal'], REMOVE])],
  ['a duration of 0', altered(DRAFT, [[...WORKOUT, 'duration_minutes'], 0])],
  ['a duration above a day', altered(DRAFT, [[...WORKOUT, 'duration_minutes'], 1441])],
  ['a fraction as duration', altered(DRAFT, [[...WORKOUT, 'duration_minutes'], 1.5])],
  ['a text as duration', altered(DRAFT, [[...WORKOUT, 'duration_minutes'], '60'])],
  ['no duration', altered(DRAFT, [[...WORKOUT, 'duration_minutes'], REMOVE])],
  ['a zone system without a zone', altered(DRAFT, [[...WORKOUT, 'zone'], null])],
  ['a zone without a zone system', altered(DRAFT, [[...WORKOUT, 'zone_system'], null])],
  ['an unknown zone system', altered(DRAFT, [[...WORKOUT, 'zone_system'], 'speed'])],
  ['a power zone above 7', altered(DRAFT, [[...WORKOUT, 'zone'], 8])],
  ['a power zone of 0', altered(DRAFT, [[...WORKOUT, 'zone'], 0])],
  ['a fraction as zone', altered(DRAFT, [[...WORKOUT, 'zone'], 2.5])],
  [
    'a heart rate zone above 5',
    altered(DRAFT, [[...WORKOUT, 'zone_system'], 'heart_rate'], [[...WORKOUT, 'zone'], 6]),
  ],
  [
    'a pace zone above 5',
    altered(DRAFT, [[...WORKOUT, 'zone_system'], 'pace'], [[...WORKOUT, 'zone'], 6]),
  ],
  ['no zone system', altered(DRAFT, [[...WORKOUT, 'zone_system'], REMOVE])],
  ['no notes', altered(DRAFT, [[...WORKOUT, 'notes'], REMOVE])],
  ['a number as notes', altered(DRAFT, [[...WORKOUT, 'notes'], 5])],
  ['no segments', altered(DRAFT, [[...WORKOUT, 'segments'], REMOVE])],
  ['an object as segments', altered(DRAFT, [[...WORKOUT, 'segments'], {}])],
  ['a text as segment', altered(DRAFT, [['workouts', 2, 'segments'], ['warm']])],
  ['an unknown segment kind', altered(DRAFT, [[...SEGMENT, 'kind'], 'sprint'])],
  ['no segment kind', altered(DRAFT, [[...SEGMENT, 'kind'], REMOVE])],
  ['0 seconds', altered(DRAFT, [[...SEGMENT, 'seconds'], 0])],
  ['a text as seconds', altered(DRAFT, [[...SEGMENT, 'seconds'], '900'])],
  ['a fraction as seconds', altered(DRAFT, [[...SEGMENT, 'seconds'], 1.5])],
  ['no seconds', altered(DRAFT, [[...SEGMENT, 'seconds'], REMOVE])],
  ['a repeat of 0', altered(DRAFT, [[...SEGMENT, 'repeat'], 0])],
  ['a repeat above 50', altered(DRAFT, [[...SEGMENT, 'repeat'], 51])],
  ['a fraction as repeat', altered(DRAFT, [[...SEGMENT, 'repeat'], 1.5])],
  ['no repeat', altered(DRAFT, [[...SEGMENT, 'repeat'], REMOVE])],
  ['a segment zone system without a zone', altered(DRAFT, [[...SEGMENT, 'zone'], null])],
  ['a segment zone without a zone system', altered(DRAFT, [[...SEGMENT, 'zone_system'], null])],
  ['a segment zone above 7', altered(DRAFT, [[...SEGMENT, 'zone'], 8])],
  ['an unknown segment zone system', altered(DRAFT, [[...SEGMENT, 'zone_system'], 'speed'])],
];

const WRONG_WEEKS: [string, unknown][] = [
  ['no body', null],
  ['a list as body', []],
  ['a text as body', 'weeks'],
  ['no weeks', {}],
  ['an object as weeks', { weeks: {} }],
  ['a text as week', { weeks: ['2026-11-16'] }],
  ['a week that is no date', altered(WEEKS, [['weeks', 0, 'week_start'], '2026-02-30'])],
  ['a week that is no Monday', altered(WEEKS, [['weeks', 0, 'week_start'], '2026-11-10'])],
  ['no week date', altered(WEEKS, [['weeks', 0, 'week_start'], REMOVE])],
  ['no plans', altered(WEEKS, [['weeks', 0, 'plans'], REMOVE])],
  ['a text as plans', altered(WEEKS, [['weeks', 0, 'plans'], 'none'])],
  ['a text as version entry', altered(WEEKS, [['weeks', 1, 'plans'], ['v1']])],
  ['an id that is no uuid', altered(WEEKS, [['weeks', 1, 'plans', 0, 'id'], 'x'])],
  ['version 0', altered(WEEKS, [['weeks', 1, 'plans', 0, 'version'], 0])],
  ['a text as version', altered(WEEKS, [['weeks', 1, 'plans', 0, 'version'], '1'])],
  ['an unknown status', altered(WEEKS, [['weeks', 1, 'plans', 0, 'status'], 'done'])],
  ['no reason', altered(WEEKS, [['weeks', 1, 'plans', 0, 'reason'], REMOVE])],
  ['a negative count', altered(WEEKS, [['weeks', 1, 'plans', 0, 'workout_count'], -1])],
  ['a fraction as count', altered(WEEKS, [['weeks', 1, 'plans', 0, 'workout_count'], 1.5])],
  ['a time that is no time', altered(WEEKS, [['weeks', 1, 'plans', 0, 'created_at'], 'then'])],
  [
    'a discarded version that was confirmed',
    altered(WEEKS, [['weeks', 1, 'plans', 0, 'confirmed_at'], '2026-11-13T23:28:07Z']),
  ],
  [
    'a confirmed version that was never confirmed',
    altered(WEEKS, [['weeks', 1, 'plans', 0, 'status'], 'confirmed']),
  ],
];

describe('PlanningApi', () => {
  let api: PlanningApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(PlanningApi);
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

  async function failsOnTheNetwork(action: Promise<unknown>, url: string): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() => backend.expectOne((req) => req.url === url));

    request.error(new ProgressEvent('error'));

    await expect(action).rejects.toThrow();
  }

  describe('weeks', () => {
    it('asks for the weeks and returns them with their versions', async () => {
      const { result, request } = await run(api.weeks(), 'GET', WEEKS_URL, WEEKS, 200);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', weeks: WEEKS.weeks });
    });

    it('returns five weeks without any plan', async () => {
      const empty = { weeks: WEEKS.weeks.map((week) => ({ ...week, plans: [] })) };

      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, empty, 200);

      expect(result).toEqual({ kind: 'ok', weeks: empty.weeks });
    });

    it('knows a confirmed version with the time it was confirmed', async () => {
      const confirmed = altered(
        WEEKS,
        [['weeks', 1, 'plans', 0, 'status'], 'confirmed'],
        [['weeks', 1, 'plans', 0, 'confirmed_at'], '2026-11-13T23:28:07.353166Z'],
      );

      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, confirmed as object, 200);

      expect(versionOf(result)).toMatchObject({
        status: 'confirmed',
        confirmed_at: '2026-11-13T23:28:07.353166Z',
      });
    });

    it.each(['draft', 'discarded'])(
      'knows a %s version without a time of confirming',
      async (status) => {
        const body = altered(WEEKS, [['weeks', 1, 'plans', 0, 'status'], status]);

        const { result } = await run(api.weeks(), 'GET', WEEKS_URL, body as object, 200);

        expect(versionOf(result)).toMatchObject({ status, confirmed_at: null });
      },
    );

    it('takes over only the known fields', async () => {
      const crowded = altered(
        WEEKS,
        [['secret'], 'x'],
        [['weeks', 1, 'owner'], 'x'],
        [['weeks', 1, 'plans', 0, 'prompt'], 'x'],
      );

      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, crowded as object, 200);

      expect(result).toEqual({ kind: 'ok', weeks: WEEKS.weeks });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_WEEKS)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.weeks(), 'GET', WEEKS_URL, bad as object | null, 200);
    });

    it.each([404, 409, 429, 500, 502])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.weeks(), 'GET', WEEKS_URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.weeks(), WEEKS_URL);
    });
  });

  describe('generate', () => {
    const URL = '/api/planning/weeks/2026-11-16/generate/';

    it('posts to the address of the week and returns the draft', async () => {
      const { result, request } = await run(api.generate('2026-11-16'), 'POST', URL, DRAFT, 201);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', plan: DRAFT as WeekPlan });
    });

    it('returns the checks of the draft, errors and warnings alike', async () => {
      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, WARNED_DRAFT, 201);

      expect(result).toMatchObject({
        plan: { report: { valid: true, findings: [{ severity: 'warning', code: 'no_free_day' }] } },
      });
    });

    it('returns a draft without any finding', async () => {
      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, VALID_DRAFT, 201);

      expect(result).toMatchObject({ plan: { report: { valid: true, findings: [] } } });
    });

    it('takes over only the known fields', async () => {
      const crowded = altered(
        DRAFT,
        [['prompt'], 'x'],
        [[...WORKOUT, 'owner'], 'x'],
        [[...SEGMENT, 'secret'], 'x'],
        [['report', 'internal'], 'x'],
        [[...FINDING, 'raw'], 'x'],
      );

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, crowded as object, 201);

      expect(result).toEqual({ kind: 'ok', plan: DRAFT });
    });

    it('copies the workouts', async () => {
      const body = altered(DRAFT) as { workouts: unknown[] };

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body, 201);

      const copy = result.kind === 'ok' ? result.plan.workouts : null;
      expect(copy).not.toBe(body.workouts);
    });

    it.each(['2026-11-1', '2026-02-30', '2026-13-45', '20261116', '../plans', '2026-11-16/x', ''])(
      'sends nothing for the week "%s"',
      async (week) => {
        const result = await api.generate(week);

        expect(result).toEqual({ kind: 'not_plannable' });
        backend.expectNone(() => true);
      },
    );

    it('says when the week cannot be planned', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: 'This week cannot be planned.', code: 'week_not_plannable' },
        404,
      );

      expect(result).toEqual({ kind: 'not_plannable' });
    });

    it('says when no provider is set up', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: 'No AI provider is set up.', code: 'not_configured' },
        409,
      );

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when the week offers no training time', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        {
          detail: 'You have no training time for this week. Enter it on the Training time page.',
          code: 'no_time',
        },
        409,
      );

      expect(result).toEqual({ kind: 'no_time' });
    });

    it.each([
      ['no body', null],
      ['a page of a proxy', PROXY_PAGE],
      ['a list as body', []],
      ['no code', { detail: 'Something.' }],
      ['a number as code', { code: 5 }],
      ['an unknown code', { code: 'weird' }],
      ['the code of the provider', { code: 'not_configured' }],
      ['the code in other letters', { code: 'NO_TIME' }],
    ])('keeps a 409 with %s as "no provider"', async (_name, body) => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        body as object | null,
        409,
      );

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when the coach gave nothing usable, and what was wrong', async () => {
      const problems = [{ path: '', message: 'The answer is not one JSON object.' }];

      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: 'The coach did not give a plan.', code: 'not_usable', problems },
        422,
      );

      expect(result).toEqual({ kind: 'not_usable', problems });
    });

    it.each([
      ['no problems', { code: 'not_usable' }],
      ['an object as problems', { problems: {} }],
      ['a text as problem', { problems: ['bad'] }],
      ['a problem without a path', { problems: [{ message: 'x' }] }],
      ['a problem without a message', { problems: [{ path: '' }] }],
      ['a number as message', { problems: [{ path: '', message: 5 }] }],
    ])('rejects an unusable-plan answer with %s', async (_name, body) => {
      await runFailing(api.generate('2026-11-16'), 'POST', URL, body, 422);
    });

    it('says when this server limits the plans', async () => {
      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('returns the provider asking to slow down as a problem with the time to wait', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        {
          detail: 'The provider is asking to slow down. Please try again in a moment.',
          code: 'rate_limited',
          retry_after: 17,
        },
        429,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider is asking to slow down. Please try again in a moment.',
        retry_after: 17,
      });
    });

    it('knows a provider that asks to slow down without saying for how long', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: 'Slow down.', code: 'rate_limited', retry_after: null },
        429,
      );

      expect(result).toMatchObject({ problem: 'rate_limited', retry_after: null });
    });

    it.each([
      [502, 'invalid_key'],
      [502, 'unexpected'],
      [502, 'not_allowed'],
      [503, 'unavailable'],
    ])('returns the problem %i %s with the text of the server', async (status, code) => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
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
      'still knows what kind of problem a %i is if a proxy replaced the answer',
      async (status, problem) => {
        const { result } = await run(api.generate('2026-11-16'), 'POST', URL, PROXY_PAGE, status);

        expect(result).toEqual({
          kind: 'provider_problem',
          problem,
          message: 'The AI provider could not be used right now. Please try again later.',
          retry_after: null,
        });
      },
    );

    it.each([
      ['an unknown code', { detail: PROVIDER_TEXT, code: 'weird' }],
      ['a number as code', { detail: PROVIDER_TEXT, code: 5 }],
      ['no code', { detail: PROVIDER_TEXT }],
      ['a list as body', []],
      ['no body', null],
    ])('takes no text from an answer with %s', async (_name, body) => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        body as object | null,
        502,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: 'unexpected',
        message: 'The AI provider could not be used right now. Please try again later.',
        retry_after: null,
      });
    });

    it('uses the fixed text if the server sends no usable one', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: '', code: 'invalid_key' },
        502,
      );

      expect(result).toMatchObject({
        problem: 'invalid_key',
        message: 'The AI provider could not be used right now. Please try again later.',
      });
    });

    it.each([
      ['a text', '30'],
      ['a fraction', 1.5],
      ['a negative number', -1],
    ])('ignores %s as time to wait', async (_name, wait) => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: 'Slow down.', code: 'rate_limited', retry_after: wait },
        429,
      );

      expect(result).toMatchObject({ problem: 'rate_limited', retry_after: null });
    });

    it('takes no time to wait from an answer without a known code', async () => {
      const { result } = await run(
        api.generate('2026-11-16'),
        'POST',
        URL,
        { detail: PROVIDER_TEXT, code: 'weird', retry_after: 30 },
        502,
      );

      expect(result).toMatchObject({ problem: 'unexpected', retry_after: null });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects a draft with %s', async (_name, bad) => {
      await runFailing(api.generate('2026-11-16'), 'POST', URL, bad as object | null, 201);
    });

    it.each([200, 400, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.generate('2026-11-16'), 'POST', URL, DRAFT, status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.generate('2026-11-16'), URL);
    });
  });

  describe('get', () => {
    const URL = `/api/planning/plans/${DRAFT_ID}/`;

    it('returns a draft with its checks', async () => {
      const { result, request } = await run(api.get(DRAFT_ID), 'GET', URL, DRAFT, 200);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', plan: DRAFT as WeekPlan });
    });

    it('returns a confirmed plan without checks', async () => {
      const { result } = await run(
        api.get(CONFIRMED_ID),
        'GET',
        `/api/planning/plans/${CONFIRMED_ID}/`,
        CONFIRMED,
        200,
      );

      expect(result).toEqual({ kind: 'ok', plan: CONFIRMED as WeekPlan });
    });

    it('knows a plan that was replaced since', async () => {
      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, SUPERSEDED, 200);

      expect(result).toMatchObject({ plan: { status: 'superseded', report: null } });
    });

    it('knows a discarded plan', async () => {
      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, DISCARDED, 200);

      expect(result).toMatchObject({ plan: { status: 'discarded', report: null } });
    });

    it('knows a version that replaces another', async () => {
      const body = altered(DRAFT, [['parent'], OTHER_ID]);

      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, body as object, 200);

      expect(result).toMatchObject({ plan: { parent: OTHER_ID } });
    });

    it.each([
      '12',
      'x',
      '../weeks/',
      `${DRAFT_ID}/confirm`,
      `../${DRAFT_ID}`,
      '',
      DRAFT_ID.toUpperCase(),
    ])('sends nothing for the id "%s" and says it is not found', async (id) => {
      const result = await api.get(id);

      expect(result).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it('says when there is no such plan', async () => {
      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, NOT_FOUND, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.get(DRAFT_ID), 'GET', URL, bad as object | null, 200);
    });

    it.each([400, 409, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.get(DRAFT_ID), 'GET', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.get(DRAFT_ID), URL);
    });
  });

  describe('confirm', () => {
    const URL = `/api/planning/plans/${DRAFT_ID}/confirm/`;
    const CONFIRMED_DRAFT = {
      ...DRAFT,
      status: 'confirmed',
      report: null,
      confirmed_at: CONFIRMED.confirmed_at,
    };

    it('posts to the confirm address and returns the confirmed plan', async () => {
      const { result, request } = await run(
        api.confirm(DRAFT_ID),
        'POST',
        URL,
        CONFIRMED_DRAFT,
        200,
      );

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', plan: CONFIRMED_DRAFT });
    });

    it('returns all findings if the plan has errors', async () => {
      const findings = [
        ...DRAFT.report.findings,
        { severity: 'warning', code: 'no_free_day', message: 'No free day.', path: '' },
      ];

      const { result } = await run(
        api.confirm(DRAFT_ID),
        'POST',
        URL,
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
      ['a text as findings', { findings: 'bad' }],
      [
        'a finding with an unknown severity',
        { findings: [{ ...DRAFT.report.findings[0], severity: 'x' }] },
      ],
      ['no body', null],
    ])('rejects a refusal with %s', async (_name, body) => {
      await runFailing(api.confirm(DRAFT_ID), 'POST', URL, body as object | null, 422);
    });

    it('says when it is no draft any more', async () => {
      const { result } = await run(api.confirm(DRAFT_ID), 'POST', URL, NOT_A_DRAFT, 409);

      expect(result).toEqual({ kind: 'not_a_draft' });
    });

    it('says when there is no such plan', async () => {
      const { result } = await run(api.confirm(DRAFT_ID), 'POST', URL, NOT_FOUND, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('sends nothing for an id that is no uuid', async () => {
      expect(await api.confirm('12')).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.confirm(DRAFT_ID), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects a confirmed plan with %s', async (_name, bad) => {
      await runFailing(api.confirm(DRAFT_ID), 'POST', URL, bad as object | null, 200);
    });

    it.each([400, 429, 500, 502])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.confirm(DRAFT_ID), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.confirm(DRAFT_ID), URL);
    });
  });

  describe('discard', () => {
    const URL = `/api/planning/plans/${DRAFT_ID}/discard/`;

    it('posts to the discard address and returns the discarded plan', async () => {
      const { result, request } = await run(api.discard(DRAFT_ID), 'POST', URL, DISCARDED, 200);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', plan: DISCARDED as WeekPlan });
    });

    it('says when it is no draft any more', async () => {
      const { result } = await run(api.discard(DRAFT_ID), 'POST', URL, NOT_A_DRAFT, 409);

      expect(result).toEqual({ kind: 'not_a_draft' });
    });

    it('says when there is no such plan', async () => {
      const { result } = await run(api.discard(DRAFT_ID), 'POST', URL, NOT_FOUND, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('sends nothing for an id that is no uuid', async () => {
      expect(await api.discard('../x')).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.discard(DRAFT_ID), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects a discarded plan with %s', async (_name, bad) => {
      await runFailing(api.discard(DRAFT_ID), 'POST', URL, bad as object | null, 200);
    });

    it.each([400, 422, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.discard(DRAFT_ID), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.discard(DRAFT_ID), URL);
    });
  });
});
