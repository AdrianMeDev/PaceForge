import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { AvailabilityApi } from './availability-api';
import { Availability, Limitation, Period, PeriodInput } from './availability-models';

const URL = '/api/availability/';
const PERIODS = '/api/availability/periods/';
const ID = '01a1d563-8869-7740-90ae-aadc415bbbeb';

// The shapes are those of the real API (replayed with curl against a real Django).
const LEVEL_LIMITS = {
  relaxed: {
    max_hard_days: 1,
    progression_warning_percent: 115,
    progression_error_percent: 130,
    easy_share_percent: 85,
  },
  normal: {
    max_hard_days: 2,
    progression_warning_percent: 120,
    progression_error_percent: 140,
    easy_share_percent: 80,
  },
  intensive: {
    max_hard_days: 3,
    progression_warning_percent: 130,
    progression_error_percent: 150,
    easy_share_percent: 75,
  },
};
const EVERY_PART = ['morning', 'afternoon', 'evening'];
const AVAILABILITY = {
  weekdays: [60, 0, 90, 0, 0, 120, 180],
  double_days: [true, false, true, true, false, true, true],
  time_windows: [
    ['evening'],
    EVERY_PART,
    ['morning', 'evening'],
    EVERY_PART,
    ['afternoon'],
    ['morning', 'afternoon'],
    EVERY_PART,
  ],
  weekly_budget_minutes: 300,
  typical_weekly_minutes: 360,
  sports: ['running', 'cycling', 'swimming', 'strength'],
  stretching: false,
  limitations: 'No running <b>x</b>',
  share_limitations_text: true,
  intensity_level: 'relaxed',
  max_hard_days: 2,
  progression_warning_percent: null,
  progression_error_percent: 160,
  easy_share_percent: null,
  level_limits: LEVEL_LIMITS,
};
const NOTHING_SAVED = {
  weekdays: [0, 0, 0, 0, 0, 0, 0],
  double_days: [true, true, true, true, true, true, true],
  time_windows: [
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
  ],
  weekly_budget_minutes: null,
  typical_weekly_minutes: null,
  sports: ['running', 'cycling', 'swimming', 'strength'],
  stretching: false,
  limitations: '',
  share_limitations_text: false,
  intensity_level: 'normal',
  max_hard_days: null,
  progression_warning_percent: null,
  progression_error_percent: null,
  easy_share_percent: null,
  level_limits: LEVEL_LIMITS,
};
const LIMITATIONS = '/api/availability/limitations/';
const ACHILLES = {
  id: '01a1d563-9a11-7c01-8a11-000000000001',
  body_part: 'achilles',
  status: 'current',
  sports: ['running'],
};
const BACK = {
  id: '01a1d563-9a11-7c01-8a11-000000000002',
  body_part: 'back',
  status: 'healed',
  sports: [],
};
const UPCOMING = {
  id: ID,
  kind: 'vacation',
  start_date: '2026-11-23',
  end_date: '2026-12-06',
  days: 14,
  status: 'upcoming',
  note: 'Mallorca <b>x</b>',
};
const CURRENT = {
  id: '01a1d563-8883-72a7-b9a5-fbd7ef81d77b',
  kind: 'illness',
  start_date: '2026-11-12',
  end_date: '2026-11-15',
  days: 4,
  status: 'current',
  note: '',
};
const PAST = {
  id: '01a1d563-889c-728a-b93d-77e30798d221',
  kind: 'other',
  start_date: '2026-10-14',
  end_date: '2026-10-24',
  days: 11,
  status: 'past',
  note: '',
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

describe('AvailabilityApi', () => {
  let api: AvailabilityApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(AvailabilityApi);
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

  const WRONG_AVAILABILITY: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'availability'],
    ['no weekdays', altered(AVAILABILITY, [['weekdays'], REMOVE])],
    ['six weekdays', altered(AVAILABILITY, [['weekdays'], [1, 2, 3, 4, 5, 6]])],
    ['eight weekdays', altered(AVAILABILITY, [['weekdays'], [1, 2, 3, 4, 5, 6, 7, 8]])],
    ['an object as weekdays', altered(AVAILABILITY, [['weekdays'], { 0: 1 }])],
    ['a text as a weekday', altered(AVAILABILITY, [['weekdays', 2], '90'])],
    ['a fraction as a weekday', altered(AVAILABILITY, [['weekdays', 2], 90.5])],
    ['a negative weekday', altered(AVAILABILITY, [['weekdays', 2], -1])],
    ['null as a weekday', altered(AVAILABILITY, [['weekdays', 2], null])],
    ['no double days', altered(AVAILABILITY, [['double_days'], REMOVE])],
    [
      'six double days',
      altered(AVAILABILITY, [['double_days'], [true, true, true, true, true, true]]),
    ],
    ['eight double days', altered(AVAILABILITY, [['double_days'], Array(8).fill(true)])],
    ['a text as double days', altered(AVAILABILITY, [['double_days'], 'ttttttt'])],
    ['a text as a double day', altered(AVAILABILITY, [['double_days', 1], 'false'])],
    ['a number as a double day', altered(AVAILABILITY, [['double_days', 1], 0])],
    ['null as a double day', altered(AVAILABILITY, [['double_days', 1], null])],
    ['null as double days', altered(AVAILABILITY, [['double_days'], null])],
    ['no time windows', altered(AVAILABILITY, [['time_windows'], REMOVE])],
    ['six time windows', altered(AVAILABILITY, [['time_windows'], Array(6).fill(EVERY_PART)])],
    ['eight time windows', altered(AVAILABILITY, [['time_windows'], Array(8).fill(EVERY_PART)])],
    ['a text as time windows', altered(AVAILABILITY, [['time_windows'], 'morning'])],
    ['an empty day', altered(AVAILABILITY, [['time_windows', 2], []])],
    ['a text as the windows of a day', altered(AVAILABILITY, [['time_windows', 2], 'morning'])],
    ['an unknown part of the day', altered(AVAILABILITY, [['time_windows', 2], ['noon']])],
    ['a part in other letters', altered(AVAILABILITY, [['time_windows', 2], ['Morning']])],
    [
      'a part twice',
      altered(AVAILABILITY, [
        ['time_windows', 2],
        ['morning', 'morning'],
      ]),
    ],
    ['a number as a part', altered(AVAILABILITY, [['time_windows', 2], [1]])],
    ['null as the windows of a day', altered(AVAILABILITY, [['time_windows', 2], null])],
    ['no sharing flag', altered(AVAILABILITY, [['share_limitations_text'], REMOVE])],
    ['a text as sharing flag', altered(AVAILABILITY, [['share_limitations_text'], 'true'])],
    ['a number as sharing flag', altered(AVAILABILITY, [['share_limitations_text'], 1])],
    ['null as sharing flag', altered(AVAILABILITY, [['share_limitations_text'], null])],
    ['no budget', altered(AVAILABILITY, [['weekly_budget_minutes'], REMOVE])],
    ['a text as budget', altered(AVAILABILITY, [['weekly_budget_minutes'], '300'])],
    ['a fraction as budget', altered(AVAILABILITY, [['weekly_budget_minutes'], 300.5])],
    ['a negative budget', altered(AVAILABILITY, [['weekly_budget_minutes'], -5])],
    ['no typical week', altered(AVAILABILITY, [['typical_weekly_minutes'], REMOVE])],
    ['a text as typical week', altered(AVAILABILITY, [['typical_weekly_minutes'], '360'])],
    ['a fraction as typical week', altered(AVAILABILITY, [['typical_weekly_minutes'], 360.5])],
    ['a negative typical week', altered(AVAILABILITY, [['typical_weekly_minutes'], -5])],
    ['no sports', altered(AVAILABILITY, [['sports'], REMOVE])],
    ['a text as sports', altered(AVAILABILITY, [['sports'], 'running'])],
    ['an object as sports', altered(AVAILABILITY, [['sports'], { running: true }])],
    ['no sport at all', altered(AVAILABILITY, [['sports'], []])],
    ['an unknown sport', altered(AVAILABILITY, [['sports'], ['running', 'golf']])],
    ['a sport in other letters', altered(AVAILABILITY, [['sports'], ['Running']])],
    ['a number as a sport', altered(AVAILABILITY, [['sports'], ['running', 5]])],
    ['a sport twice', altered(AVAILABILITY, [['sports'], ['running', 'running']])],
    ['null as sports', altered(AVAILABILITY, [['sports'], null])],
    ['no stretching flag', altered(AVAILABILITY, [['stretching'], REMOVE])],
    ['a text as stretching flag', altered(AVAILABILITY, [['stretching'], 'true'])],
    ['a number as stretching flag', altered(AVAILABILITY, [['stretching'], 1])],
    ['null as stretching flag', altered(AVAILABILITY, [['stretching'], null])],
    ['no limitations', altered(AVAILABILITY, [['limitations'], REMOVE])],
    ['a number as limitations', altered(AVAILABILITY, [['limitations'], 5])],
    ['null as limitations', altered(AVAILABILITY, [['limitations'], null])],
    ['no intensity level', altered(AVAILABILITY, [['intensity_level'], REMOVE])],
    ['an unknown intensity level', altered(AVAILABILITY, [['intensity_level'], 'brutal'])],
    ['a level in other letters', altered(AVAILABILITY, [['intensity_level'], 'Normal'])],
    ['null as intensity level', altered(AVAILABILITY, [['intensity_level'], null])],
    ['no own hard days', altered(AVAILABILITY, [['max_hard_days'], REMOVE])],
    ['a text as own hard days', altered(AVAILABILITY, [['max_hard_days'], '2'])],
    ['a fraction as own warning', altered(AVAILABILITY, [['progression_warning_percent'], 120.5])],
    ['a negative own error', altered(AVAILABILITY, [['progression_error_percent'], -1])],
    ['no own easy share', altered(AVAILABILITY, [['easy_share_percent'], REMOVE])],
    ['no level limits', altered(AVAILABILITY, [['level_limits'], REMOVE])],
    ['a list as level limits', altered(AVAILABILITY, [['level_limits'], []])],
    ['a level without limits', altered(AVAILABILITY, [['level_limits', 'intensive'], REMOVE])],
    ['null as the limits of a level', altered(AVAILABILITY, [['level_limits', 'normal'], null])],
    [
      'a limit of a level missing',
      altered(AVAILABILITY, [['level_limits', 'normal', 'easy_share_percent'], REMOVE]),
    ],
    [
      'null as a limit of a level',
      altered(AVAILABILITY, [['level_limits', 'relaxed', 'max_hard_days'], null]),
    ],
    [
      'a text as a limit of a level',
      altered(AVAILABILITY, [['level_limits', 'relaxed', 'progression_error_percent'], '130']),
    ],
  ];

  const WRONG_LIMITATIONS: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'limitation'],
    ['no id', altered(ACHILLES, [['id'], REMOVE])],
    ['a number as id', altered(ACHILLES, [['id'], 5])],
    ['no body part', altered(ACHILLES, [['body_part'], REMOVE])],
    ['an unknown body part', altered(ACHILLES, [['body_part'], 'elbow'])],
    ['a body part in other letters', altered(ACHILLES, [['body_part'], 'Knee'])],
    ['no status', altered(ACHILLES, [['status'], REMOVE])],
    ['an unknown status', altered(ACHILLES, [['status'], 'chronic'])],
    ['no sports', altered(ACHILLES, [['sports'], REMOVE])],
    ['a text as sports', altered(ACHILLES, [['sports'], 'running'])],
    ['an unknown sport', altered(ACHILLES, [['sports'], ['golf']])],
    ['a sport twice', altered(ACHILLES, [['sports'], ['running', 'running']])],
    ['a number as a sport', altered(ACHILLES, [['sports', 0], 5])],
    ['null as sports', altered(ACHILLES, [['sports'], null])],
  ];

  const WRONG_PERIODS: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'period'],
    ['no id', altered(UPCOMING, [['id'], REMOVE])],
    ['a number as id', altered(UPCOMING, [['id'], 5])],
    ['an unknown kind', altered(UPCOMING, [['kind'], 'holiday'])],
    ['no start', altered(UPCOMING, [['start_date'], REMOVE])],
    ['a start that is no date', altered(UPCOMING, [['start_date'], 'soon'])],
    ['a start with a time', altered(UPCOMING, [['start_date'], '2026-11-23T10:00:00Z'])],
    ['a number as start', altered(UPCOMING, [['start_date'], 20261123])],
    ['no end', altered(UPCOMING, [['end_date'], REMOVE])],
    ['an end that is no date', altered(UPCOMING, [['end_date'], '6 December'])],
    ['no days', altered(UPCOMING, [['days'], REMOVE])],
    ['a text as days', altered(UPCOMING, [['days'], '14'])],
    ['a fraction as days', altered(UPCOMING, [['days'], 1.5])],
    ['zero days', altered(UPCOMING, [['days'], 0])],
    ['an unknown status', altered(UPCOMING, [['status'], 'ongoing'])],
    ['no status', altered(UPCOMING, [['status'], REMOVE])],
    ['no note', altered(UPCOMING, [['note'], REMOVE])],
    ['null as note', altered(UPCOMING, [['note'], null])],
    ['a number as note', altered(UPCOMING, [['note'], 5])],
  ];

  describe('get', () => {
    it('returns the availability', async () => {
      const { result, request } = await run(api.get(), 'GET', URL, AVAILABILITY, 200);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', availability: AVAILABILITY as Availability });
    });

    it('returns zeros and no budget for a user who saved nothing', async () => {
      const { result } = await run(api.get(), 'GET', URL, NOTHING_SAVED, 200);

      expect(result).toEqual({ kind: 'ok', availability: NOTHING_SAVED });
    });

    it('takes over the double days and the time windows as copies', async () => {
      const body = altered(AVAILABILITY) as {
        double_days: boolean[];
        time_windows: string[][];
      };

      const { result } = await run(api.get(), 'GET', URL, body, 200);

      expect(result).toMatchObject({
        availability: {
          double_days: AVAILABILITY.double_days,
          time_windows: AVAILABILITY.time_windows,
        },
      });
      if (result.kind !== 'ok') {
        throw new Error('expected the availability');
      }
      expect(result.availability.double_days).not.toBe(body.double_days);
      expect(result.availability.time_windows[0]).not.toBe(body.time_windows[0]);
    });

    it('takes over only the known limits of the known levels', async () => {
      const body = altered(
        AVAILABILITY,
        [['level_limits', 'brutal'], LEVEL_LIMITS.intensive],
        [['level_limits', 'normal', 'rest_days'], 1],
      );

      const { result } = await run(api.get(), 'GET', URL, body as object, 200);

      expect(result).toEqual({ kind: 'ok', availability: AVAILABILITY });
    });

    it('takes over only the known fields and copies the weekdays', async () => {
      const body = altered(AVAILABILITY, [['owner'], 'x'], [['internal'], { secret: 1 }]);

      const { result } = await run(api.get(), 'GET', URL, body as object, 200);

      expect(result).toEqual({ kind: 'ok', availability: AVAILABILITY });
      expect(result).not.toHaveProperty('availability.owner');
      const weekdays = result.kind === 'ok' ? result.availability.weekdays : null;
      expect(weekdays).not.toBe((body as { weekdays: number[] }).weekdays);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.get(), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_AVAILABILITY)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.get(), 'GET', URL, bad as object | null, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.get(), 'GET', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.get();
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === URL));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('save', () => {
    it('patches only the fields given and returns the whole availability', async () => {
      const { result, request } = await run(
        api.save({ weekly_budget_minutes: 300 }),
        'PATCH',
        URL,
        AVAILABILITY,
        200,
      );

      expect(request.request.body).toEqual({ weekly_budget_minutes: 300 });
      expect(result).toEqual({ kind: 'ok', availability: AVAILABILITY });
    });

    it('patches the typical week alone, and a removed one as null', async () => {
      const set = await run(
        api.save({ typical_weekly_minutes: 360 }),
        'PATCH',
        URL,
        AVAILABILITY,
        200,
      );
      const cleared = await run(
        api.save({ typical_weekly_minutes: null }),
        'PATCH',
        URL,
        NOTHING_SAVED,
        200,
      );

      expect(set.request.request.body).toEqual({ typical_weekly_minutes: 360 });
      expect(cleared.request.request.body).toEqual({ typical_weekly_minutes: null });
      expect(cleared.result).toEqual({ kind: 'ok', availability: NOTHING_SAVED });
    });

    it('takes over a typical week of zero, which is no week', async () => {
      const { result } = await run(
        api.get(),
        'GET',
        URL,
        altered(AVAILABILITY, [['typical_weekly_minutes'], 0]) as object,
        200,
      );

      expect(result).toMatchObject({ availability: { typical_weekly_minutes: 0 } });
    });

    it('patches the sports and the stretching flag alone', async () => {
      const sports = await run(
        api.save({ sports: ['running'] }),
        'PATCH',
        URL,
        altered(AVAILABILITY, [['sports'], ['running']]) as object,
        200,
      );
      const stretching = await run(
        api.save({ stretching: true }),
        'PATCH',
        URL,
        altered(AVAILABILITY, [['stretching'], true]) as object,
        200,
      );

      expect(sports.request.request.body).toEqual({ sports: ['running'] });
      expect(stretching.request.request.body).toEqual({ stretching: true });
      expect(sports.result).toMatchObject({ availability: { sports: ['running'] } });
      expect(stretching.result).toMatchObject({ availability: { stretching: true } });
    });

    it('patches the double days and the time windows alone', async () => {
      const doubleDays = [false, true, true, true, true, true, true];
      const windows = [['morning'], ...Array(6).fill(EVERY_PART)] as (
        'morning' | 'afternoon' | 'evening'
      )[][];

      const days = await run(
        api.save({ double_days: doubleDays }),
        'PATCH',
        URL,
        altered(AVAILABILITY, [['double_days'], doubleDays]) as object,
        200,
      );
      const parts = await run(
        api.save({ time_windows: windows }),
        'PATCH',
        URL,
        altered(AVAILABILITY, [['time_windows'], windows]) as object,
        200,
      );

      expect(days.request.request.body).toEqual({ double_days: doubleDays });
      expect(parts.request.request.body).toEqual({ time_windows: windows });
      expect(days.result).toMatchObject({ availability: { double_days: doubleDays } });
      expect(parts.result).toMatchObject({ availability: { time_windows: windows } });
    });

    it('returns the message about the time windows', async () => {
      const refusal = {
        time_windows: [
          'Enter seven lists of parts of the day, Monday first, each with at least one of: morning, afternoon, evening.',
        ],
      };

      const { result } = await run(api.save({ time_windows: [] }), 'PATCH', URL, refusal, 400);

      expect(result).toEqual({ kind: 'invalid', errors: refusal.time_windows, fields: refusal });
    });

    it('patches the intensity level and own limits, a removed one as null', async () => {
      const changes = {
        intensity_level: 'intensive' as const,
        max_hard_days: null,
        progression_warning_percent: 110,
      };
      const answer = altered(
        AVAILABILITY,
        [['intensity_level'], 'intensive'],
        [['max_hard_days'], null],
        [['progression_warning_percent'], 110],
      );

      const { result, request } = await run(api.save(changes), 'PATCH', URL, answer as object, 200);

      expect(request.request.body).toEqual(changes);
      expect(result).toMatchObject({
        kind: 'ok',
        availability: {
          intensity_level: 'intensive',
          max_hard_days: null,
          progression_warning_percent: 110,
          progression_error_percent: 160,
          level_limits: LEVEL_LIMITS,
        },
      });
    });

    it('returns the messages of the own limits by field', async () => {
      const refusal = {
        progression_warning_percent: [
          'The warning limit (135 %) must be below the error limit (130 %).',
        ],
      };

      const { result } = await run(
        api.save({ intensity_level: 'relaxed' }),
        'PATCH',
        URL,
        refusal,
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: refusal.progression_warning_percent,
        fields: refusal,
      });
    });

    it('takes over the sports as a copy, in the order of the server', async () => {
      const body = altered(AVAILABILITY, [['sports'], ['cycling', 'strength']]) as {
        sports: string[];
      };

      const { result } = await run(api.get(), 'GET', URL, body, 200);

      const sports = result.kind === 'ok' ? result.availability.sports : null;
      expect(sports).toEqual(['cycling', 'strength']);
      expect(sports).not.toBe(body.sports);
    });

    it('sends everything as it is, a removed budget as null', async () => {
      const changes = {
        weekdays: [60, 0, 90, 0, 0, 120, 180],
        weekly_budget_minutes: null,
        typical_weekly_minutes: null,
        limitations: 'Knee',
      };

      const { request } = await run(api.save(changes), 'PATCH', URL, AVAILABILITY, 200);

      expect(request.request.body).toEqual(changes);
    });

    it('returns the messages by field and as one list', async () => {
      const { result } = await run(
        api.save({ weekdays: [1] }),
        'PATCH',
        URL,
        {
          weekdays: ['Enter seven numbers of minutes, Monday first.'],
          weekly_budget_minutes: ['Enter whole minutes between 0 and 10080.'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          'Enter seven numbers of minutes, Monday first.',
          'Enter whole minutes between 0 and 10080.',
        ],
        fields: {
          weekdays: ['Enter seven numbers of minutes, Monday first.'],
          weekly_budget_minutes: ['Enter whole minutes between 0 and 10080.'],
        },
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
      ['a list', ['x']],
      ['messages that are no text', { weekdays: [5, null] }],
    ])('uses a fixed message for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.save({}), 'PATCH', URL, reply, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.save({}), 'PATCH', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_AVAILABILITY)('rejects a saved answer with %s', async (_name, bad) => {
      await runFailing(api.save({}), 'PATCH', URL, bad as object | null, 200);
    });

    it.each([201, 404, 405, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.save({}), 'PATCH', URL, 'oops', status);
    });
  });

  describe('listPeriods', () => {
    it('returns the periods in the order sent', async () => {
      const { result, request } = await run(
        api.listPeriods(),
        'GET',
        PERIODS,
        [CURRENT, UPCOMING, PAST],
        200,
      );

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', periods: [CURRENT, UPCOMING, PAST] as Period[] });
    });

    it('returns an empty list', async () => {
      const { result } = await run(api.listPeriods(), 'GET', PERIODS, [], 200);

      expect(result).toEqual({ kind: 'ok', periods: [] });
    });

    it('takes over only the known fields', async () => {
      const crowded = altered(UPCOMING, [['owner'], 'x'], [['internal'], { secret: 1 }]);

      const { result } = await run(api.listPeriods(), 'GET', PERIODS, [crowded] as object[], 200);

      expect(result).toEqual({ kind: 'ok', periods: [UPCOMING] });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.listPeriods(), 'GET', PERIODS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PERIODS.slice(3))(
      'rejects a list holding a period with %s',
      async (_name, bad) => {
        await runFailing(api.listPeriods(), 'GET', PERIODS, [UPCOMING, bad] as object[], 200);
      },
    );

    it.each([null, 5, 'period', []])(
      'rejects a list holding %j instead of a period',
      async (item) => {
        await runFailing(api.listPeriods(), 'GET', PERIODS, [item] as object[], 200);
      },
    );

    it.each([
      ['no body', null],
      ['a text', 'periods'],
      ['an object instead of a list', UPCOMING],
    ])('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.listPeriods(), 'GET', PERIODS, bad, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.listPeriods(), 'GET', PERIODS, 'oops', status);
    });
  });

  describe('createPeriod', () => {
    const INPUT: PeriodInput = {
      kind: 'vacation',
      start_date: '2026-11-23',
      end_date: '2026-12-06',
      note: 'Mallorca <b>x</b>',
    };

    it('posts the input as it is and returns the period', async () => {
      const { result, request } = await run(
        api.createPeriod(INPUT),
        'POST',
        PERIODS,
        UPCOMING,
        201,
      );

      expect(request.request.body).toEqual(INPUT);
      expect(result).toEqual({ kind: 'ok', period: UPCOMING as Period });
    });

    it('leaves out the note when there is none', async () => {
      const input: PeriodInput = {
        kind: 'illness',
        start_date: '2026-11-12',
        end_date: '2026-11-15',
      };

      const { request } = await run(api.createPeriod(input), 'POST', PERIODS, CURRENT, 201);

      expect(request.request.body).toEqual(input);
    });

    it('returns the messages by field and as one list', async () => {
      const { result } = await run(
        api.createPeriod(INPUT),
        'POST',
        PERIODS,
        {
          end_date: ['The end cannot be before the start.'],
          kind: ['"holiday" is not a valid choice.'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The end cannot be before the start.', '"holiday" is not a valid choice.'],
        fields: {
          end_date: ['The end cannot be before the start.'],
          kind: ['"holiday" is not a valid choice.'],
        },
      });
    });

    it('keeps the message about the limit under non_field_errors', async () => {
      const { result } = await run(
        api.createPeriod(INPUT),
        'POST',
        PERIODS,
        { non_field_errors: ['You can have at most 100 periods. Delete one first.'] },
        400,
      );

      expect(result).toMatchObject({
        errors: ['You can have at most 100 periods. Delete one first.'],
        fields: { non_field_errors: ['You can have at most 100 periods. Delete one first.'] },
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
    ])('uses a fixed message for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.createPeriod(INPUT), 'POST', PERIODS, reply, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.createPeriod(INPUT), 'POST', PERIODS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PERIODS)('rejects a created answer with %s', async (_name, bad) => {
      await runFailing(api.createPeriod(INPUT), 'POST', PERIODS, bad as object | null, 201);
    });

    it.each([200, 404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.createPeriod(INPUT), 'POST', PERIODS, 'oops', status);
    });
  });

  describe('updatePeriod', () => {
    const ADDRESS = `${PERIODS}${ID}/`;

    it('patches only the fields given and returns the period', async () => {
      const { result, request } = await run(
        api.updatePeriod(ID, { note: 'changed' }),
        'PATCH',
        ADDRESS,
        { ...UPCOMING, note: 'changed' },
        200,
      );

      expect(request.request.body).toEqual({ note: 'changed' });
      expect(result).toMatchObject({ kind: 'ok', period: { id: ID, note: 'changed' } });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(
        api.updatePeriod('a/b?c', { note: 'x' }),
        'PATCH',
        `${PERIODS}a%2Fb%3Fc/`,
        {},
        404,
      );

      expect(request.request.url).toBe(`${PERIODS}a%2Fb%3Fc/`);
    });

    it('returns the messages when the change is refused', async () => {
      const { result } = await run(
        api.updatePeriod(ID, { end_date: '2026-11-01' }),
        'PATCH',
        ADDRESS,
        { end_date: ['The end cannot be before the start.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The end cannot be before the start.'],
        fields: { end_date: ['The end cannot be before the start.'] },
      });
    });

    it('says when the period does not exist or belongs to someone else', async () => {
      const { result } = await run(
        api.updatePeriod(ID, { note: 'x' }),
        'PATCH',
        ADDRESS,
        { detail: 'No UnavailablePeriod matches the given query.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.updatePeriod(ID, {}), 'PATCH', ADDRESS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PERIODS)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.updatePeriod(ID, {}), 'PATCH', ADDRESS, bad as object | null, 200);
    });

    it.each([201, 405, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.updatePeriod(ID, {}), 'PATCH', ADDRESS, 'oops', status);
    });
  });

  describe('deletePeriod', () => {
    const ADDRESS = `${PERIODS}${ID}/`;

    it('deletes the period', async () => {
      const { result, request } = await run(api.deletePeriod(ID), 'DELETE', ADDRESS, null, 204);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'deleted' });
    });

    it('says when the period does not exist or belongs to someone else', async () => {
      const { result } = await run(api.deletePeriod(ID), 'DELETE', ADDRESS, 'Not found', 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('writes the id safely into the address', async () => {
      const { request } = await run(
        api.deletePeriod('a/b'),
        'DELETE',
        `${PERIODS}a%2Fb/`,
        null,
        404,
      );

      expect(request.request.url).toBe(`${PERIODS}a%2Fb/`);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.deletePeriod(ID), 'DELETE', ADDRESS, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([200, 400, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.deletePeriod(ID), 'DELETE', ADDRESS, 'oops', status);
    });
  });

  describe('limitations', () => {
    const ADDRESS = `${LIMITATIONS}${ACHILLES.id}/`;

    describe('listLimitations', () => {
      it('returns the entries in the order sent', async () => {
        const { result, request } = await run(
          api.listLimitations(),
          'GET',
          LIMITATIONS,
          [ACHILLES, BACK],
          200,
        );

        expect(request.request.body).toBeNull();
        expect(result).toEqual({ kind: 'ok', limitations: [ACHILLES, BACK] as Limitation[] });
      });

      it('returns an empty list', async () => {
        const { result } = await run(api.listLimitations(), 'GET', LIMITATIONS, [], 200);

        expect(result).toEqual({ kind: 'ok', limitations: [] });
      });

      it('takes over only the known fields and copies the sports', async () => {
        const crowded = altered(ACHILLES, [['owner'], 'x'], [['note'], 'secret']) as {
          sports: string[];
        };

        const { result } = await run(
          api.listLimitations(),
          'GET',
          LIMITATIONS,
          [crowded] as object[],
          200,
        );

        expect(result).toEqual({ kind: 'ok', limitations: [ACHILLES] });
        if (result.kind !== 'ok') {
          throw new Error('expected the list');
        }
        expect(result.limitations[0].sports).not.toBe(crowded.sports);
      });

      it.each([401, 403])('says when the session is gone (%i)', async (status) => {
        const { result } = await run(api.listLimitations(), 'GET', LIMITATIONS, NO_SESSION, status);

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it.each(WRONG_LIMITATIONS.slice(3))(
        'rejects a list holding an entry with %s',
        async (_name, bad) => {
          await runFailing(
            api.listLimitations(),
            'GET',
            LIMITATIONS,
            [ACHILLES, bad] as object[],
            200,
          );
        },
      );

      it.each([null, 5, 'entry', []])(
        'rejects a list holding %j instead of an entry',
        async (item) => {
          await runFailing(api.listLimitations(), 'GET', LIMITATIONS, [item] as object[], 200);
        },
      );

      it.each([
        ['no body', null],
        ['a text', 'limitations'],
        ['an object instead of a list', ACHILLES],
      ])('rejects an answer with %s', async (_name, bad) => {
        await runFailing(api.listLimitations(), 'GET', LIMITATIONS, bad, 200);
      });

      it.each([404, 500])('rejects the unexpected status %i', async (status) => {
        await runFailing(api.listLimitations(), 'GET', LIMITATIONS, 'oops', status);
      });
    });

    describe('createLimitation', () => {
      it('posts the input as it is and returns the entry', async () => {
        const input = { body_part: 'achilles' as const, sports: ['running' as const] };

        const { result, request } = await run(
          api.createLimitation(input),
          'POST',
          LIMITATIONS,
          ACHILLES,
          201,
        );

        expect(request.request.body).toEqual(input);
        expect(result).toEqual({ kind: 'ok', limitation: ACHILLES });
      });

      it('leaves out what is not given', async () => {
        const { request } = await run(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          BACK,
          201,
        );

        expect(request.request.body).toEqual({ body_part: 'back' });
      });

      it('returns the messages by field and as one list', async () => {
        const refusal = {
          body_part: ['Choose one of: foot, ankle.'],
          sports: ['Choose any of: running, or none.'],
        };

        const { result } = await run(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          refusal,
          400,
        );

        expect(result).toEqual({
          kind: 'invalid',
          errors: [...refusal.body_part, ...refusal.sports],
          fields: refusal,
        });
      });

      it('keeps the message about the limit under non_field_errors', async () => {
        const refusal = {
          non_field_errors: ['You can have at most 50 limitations. Delete one first.'],
        };

        const { result } = await run(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          refusal,
          400,
        );

        expect(result).toEqual({
          kind: 'invalid',
          errors: refusal.non_field_errors,
          fields: refusal,
        });
      });

      it.each([401, 403])('says when the session is gone (%i)', async (status) => {
        const { result } = await run(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          NO_SESSION,
          status,
        );

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it.each(WRONG_LIMITATIONS)('rejects an answer with %s', async (_name, bad) => {
        await runFailing(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          bad as object | null,
          201,
        );
      });

      it.each([200, 404, 500])('rejects the unexpected status %i', async (status) => {
        await runFailing(
          api.createLimitation({ body_part: 'back' }),
          'POST',
          LIMITATIONS,
          'oops',
          status,
        );
      });
    });

    describe('updateLimitation', () => {
      it('patches only the fields given and returns the entry', async () => {
        const healed = altered(ACHILLES, [['status'], 'healed']);

        const { result, request } = await run(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          healed as object,
          200,
        );

        expect(request.request.body).toEqual({ status: 'healed' });
        expect(result).toMatchObject({ kind: 'ok', limitation: { status: 'healed' } });
      });

      it('writes the id safely into the address', async () => {
        const { request } = await run(
          api.updateLimitation('a/b', { status: 'healed' }),
          'PATCH',
          `${LIMITATIONS}a%2Fb/`,
          'Not found',
          404,
        );

        expect(request.request.url).toBe(`${LIMITATIONS}a%2Fb/`);
      });

      it('returns the messages when the change is refused', async () => {
        const refusal = { status: ['Choose one of: current, healed.'] };

        const { result } = await run(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          refusal,
          400,
        );

        expect(result).toEqual({ kind: 'invalid', errors: refusal.status, fields: refusal });
      });

      it('says when the entry does not exist or belongs to someone else', async () => {
        const { result } = await run(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          'Not found',
          404,
        );

        expect(result).toEqual({ kind: 'not_found' });
      });

      it.each([401, 403])('says when the session is gone (%i)', async (status) => {
        const { result } = await run(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          NO_SESSION,
          status,
        );

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it.each(WRONG_LIMITATIONS)('rejects an answer with %s', async (_name, bad) => {
        await runFailing(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          bad as object | null,
          200,
        );
      });

      it.each([201, 500])('rejects the unexpected status %i', async (status) => {
        await runFailing(
          api.updateLimitation(ACHILLES.id, { status: 'healed' }),
          'PATCH',
          ADDRESS,
          'oops',
          status,
        );
      });
    });

    describe('deleteLimitation', () => {
      it('deletes the entry', async () => {
        const { result, request } = await run(
          api.deleteLimitation(ACHILLES.id),
          'DELETE',
          ADDRESS,
          null,
          204,
        );

        expect(request.request.body).toBeNull();
        expect(result).toEqual({ kind: 'deleted' });
      });

      it('says when the entry does not exist or belongs to someone else', async () => {
        const { result } = await run(
          api.deleteLimitation(ACHILLES.id),
          'DELETE',
          ADDRESS,
          'Not found',
          404,
        );

        expect(result).toEqual({ kind: 'not_found' });
      });

      it('writes the id safely into the address', async () => {
        const { request } = await run(
          api.deleteLimitation('a/b'),
          'DELETE',
          `${LIMITATIONS}a%2Fb/`,
          null,
          404,
        );

        expect(request.request.url).toBe(`${LIMITATIONS}a%2Fb/`);
      });

      it.each([401, 403])('says when the session is gone (%i)', async (status) => {
        const { result } = await run(
          api.deleteLimitation(ACHILLES.id),
          'DELETE',
          ADDRESS,
          NO_SESSION,
          status,
        );

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it.each([200, 400, 500])('rejects the unexpected status %i', async (status) => {
        await runFailing(api.deleteLimitation(ACHILLES.id), 'DELETE', ADDRESS, 'oops', status);
      });
    });
  });
});
