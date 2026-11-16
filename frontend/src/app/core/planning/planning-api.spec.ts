import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { PlanningApi } from './planning-api';
import { EditedPlan, ListWeeksResult, WeekPlan, Workout } from './planning-models';

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
  note: '',
  rationale: 'Base week with one tempo session.',
  export: null,
  parent: null,
  created_at: '2026-11-13T23:27:53.638352Z',
  confirmed_at: null,
  workouts: [
    {
      lineage: '01a1d73d-aaaa-7000-8000-000000000001',
      day: '2026-11-16',
      sport: 'cycling',
      title: 'Endurance ride',
      goal: 'endurance',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 2,
      notes: 'Keep it easy',
      slot: null,
      stretching_minutes: 0,
      exercises: [],
      target: null,
      export: null,
      segments: [],
    },
    {
      lineage: '01a1d73d-aaaa-7000-8000-000000000002',
      day: '2026-11-18',
      sport: 'cycling',
      title: 'Tempo ride',
      goal: 'tempo',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 3,
      notes: 'Keep it easy',
      slot: null,
      stretching_minutes: 0,
      exercises: [],
      target: null,
      export: null,
      segments: [],
    },
    {
      lineage: '01a1d73d-aaaa-7000-8000-000000000003',
      day: '2026-11-20',
      sport: 'cycling',
      title: 'Intervals',
      goal: 'threshold',
      duration_minutes: 60,
      zone_system: null,
      zone: null,
      notes: 'Keep it easy',
      slot: null,
      stretching_minutes: 0,
      exercises: [],
      target: null,
      export: null,
      segments: [
        { kind: 'warmup', seconds: 900, repeat: 1, zone_system: 'power', zone: 2, target: null },
        { kind: 'work', seconds: 600, repeat: 3, zone_system: 'power', zone: 4, target: null },
        { kind: 'recovery', seconds: 300, repeat: 3, zone_system: 'power', zone: 1, target: null },
        { kind: 'cooldown', seconds: 600, repeat: 1, zone_system: 'power', zone: 1, target: null },
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
  note: '',
  rationale: 'Easy week',
  export: null,
  parent: null,
  created_at: '2026-11-13T23:28:07.281568Z',
  confirmed_at: '2026-11-13T23:28:07.353166Z',
  workouts: [
    {
      lineage: '01a1d73d-aaaa-7000-8000-000000000004',
      day: '2026-11-23',
      sport: 'cycling',
      title: 'Endurance ride',
      goal: 'endurance',
      duration_minutes: 60,
      zone_system: 'power',
      zone: 2,
      notes: '',
      slot: null,
      stretching_minutes: 0,
      exercises: [],
      target: null,
      export: null,
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
    { week_start: '2026-11-09', season: null, plans: [] },
    { week_start: '2026-11-16', season: null, plans: [VERSION] },
    { week_start: '2026-11-23', season: null, plans: [] },
    { week_start: '2026-11-30', season: null, plans: [] },
    { week_start: '2026-12-07', season: null, plans: [] },
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

/** A confirmed plan as the server answers after confirming (no report, not sent yet). */
function CONFIRMED_ANSWER() {
  return {
    ...DRAFT,
    status: 'confirmed',
    report: null,
    confirmed_at: CONFIRMED.confirmed_at,
    export: { synced: 0, failed: 0, not_sent: 3, older: 0 },
    workouts: DRAFT.workouts.map((workout) => ({ ...workout, export: exported('not_sent') })),
  };
}

const SENT_AT = '2026-11-14T08:00:00Z';

/** The `export` of a workout as the server writes it. */
function exported(status: string, error_code = '', pushed_at: string | null = null) {
  return { status, error_code, pushed_at };
}

const WORKOUT = ['workouts', 0] as const;
const SEGMENT = ['workouts', 2, 'segments', 0] as const;
const FINDING = ['report', 'findings', 0] as const;

/** Answers that are no plan: each must make a call that returns a plan reject. */
const SQUAT = {
  name: 'Goblet squat',
  region: 'legs',
  equipment: 'dumbbells',
  sets: 3,
  reps: 10,
  seconds: null,
  rpe: 7,
  rest_seconds: 90,
};
const PLANK = {
  name: 'Plank',
  region: 'core',
  equipment: 'bodyweight',
  sets: 3,
  reps: null,
  seconds: 45,
  rpe: null,
  rest_seconds: null,
};

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
  ['no note', altered(DRAFT, [['note'], REMOVE])],
  ['a number as note', altered(DRAFT, [['note'], 5])],
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
  ['no time of day', altered(DRAFT, [[...WORKOUT, 'slot'], REMOVE])],
  ['an unknown time of day', altered(DRAFT, [[...WORKOUT, 'slot'], 'noon'])],
  ['a time of day in other letters', altered(DRAFT, [[...WORKOUT, 'slot'], 'Morning'])],
  ['an empty text as time of day', altered(DRAFT, [[...WORKOUT, 'slot'], ''])],
  ['a number as time of day', altered(DRAFT, [[...WORKOUT, 'slot'], 5])],
  ['no lineage', altered(DRAFT, [[...WORKOUT, 'lineage'], REMOVE])],
  ['null as lineage', altered(DRAFT, [[...WORKOUT, 'lineage'], null])],
  ['a lineage that is no uuid', altered(DRAFT, [[...WORKOUT, 'lineage'], 'x'])],
  ['a number as lineage', altered(DRAFT, [[...WORKOUT, 'lineage'], 5])],
  ['no stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], REMOVE])],
  ['null as stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], null])],
  ['a text as stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], '10'])],
  ['a fraction as stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], 7.5])],
  ['negative stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], -1])],
  ['more than an hour of stretching', altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], 61])],
  ['no exercises', altered(DRAFT, [[...WORKOUT, 'exercises'], REMOVE])],
  ['null as exercises', altered(DRAFT, [[...WORKOUT, 'exercises'], null])],
  ['an object as exercises', altered(DRAFT, [[...WORKOUT, 'exercises'], {}])],
  ['more than 15 exercises', altered(DRAFT, [[...WORKOUT, 'exercises'], Array(16).fill(SQUAT)])],
  ['a text as an exercise', altered(DRAFT, [[...WORKOUT, 'exercises'], ['squat']])],
  [
    'an exercise without a name',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, name: '' }]]),
  ],
  [
    'an unknown region',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, region: 'arms' }]]),
  ],
  [
    'unknown equipment',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, equipment: 'barbell' }]]),
  ],
  ['zero sets', altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, sets: 0 }]])],
  ['fractional sets', altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, sets: 2.5 }]])],
  [
    'reps and seconds both',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, seconds: 45 }]]),
  ],
  [
    'neither reps nor seconds',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, reps: null }]]),
  ],
  ['a text as RPE', altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, rpe: '7' }]])],
  [
    'no rest field',
    altered(DRAFT, [[...WORKOUT, 'exercises'], [{ ...SQUAT, rest_seconds: undefined }]]),
  ],
  ['no target', altered(DRAFT, [[...WORKOUT, 'target'], REMOVE])],
  ['a text as target', altered(DRAFT, [[...WORKOUT, 'target'], '138-188 W'])],
  [
    'a list as target',
    altered(DRAFT, [
      [...WORKOUT, 'target'],
      [138, 188],
    ]),
  ],
  [
    'a target that falls',
    altered(DRAFT, [[...WORKOUT, 'target'], { low: 188, high: 138, unit: 'W' }]),
  ],
  [
    'a target with an unknown unit',
    altered(DRAFT, [[...WORKOUT, 'target'], { low: 138, high: 188, unit: 'kJ' }]),
  ],
  [
    'a target with a fraction',
    altered(DRAFT, [[...WORKOUT, 'target'], { low: 138.5, high: 188, unit: 'W' }]),
  ],
  ['no target on a segment', altered(DRAFT, [[...SEGMENT, 'target'], REMOVE])],
  ['no export', altered(DRAFT, [[...WORKOUT, 'export'], REMOVE])],
  ['a text as export', altered(DRAFT, [[...WORKOUT, 'export'], 'synced'])],
  ['an unknown export status', altered(DRAFT, [[...WORKOUT, 'export'], exported('queued')])],
  [
    'a failure without a code',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('failed', '', SENT_AT)]),
  ],
  [
    'a code without a failure',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('synced', 'rejected', SENT_AT)]),
  ],
  [
    'an unknown error code',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('failed', 'boom', SENT_AT)]),
  ],
  [
    'a workout that was sent at no time',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('synced', '', null)]),
  ],
  [
    'a workout that was not sent but has a time',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('not_sent', '', SENT_AT)]),
  ],
  [
    'a time of sending that is no time',
    altered(DRAFT, [[...WORKOUT, 'export'], exported('synced', '', 'yesterday')]),
  ],
  ['no summary of the export', altered(DRAFT, [['export'], REMOVE])],
  ['a text as summary', altered(DRAFT, [['export'], 'none'])],
  [
    'a summary with a negative count',
    altered(DRAFT, [['export'], { synced: -1, failed: 0, not_sent: 0, older: 0 }]),
  ],
  ['a summary without a count', altered(DRAFT, [['export'], { synced: 1 }])],
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

const SEASON = {
  phase: 'build',
  recovery: false,
  target_minutes: 300,
  minutes: [
    { sport: 'running', minutes: 200 },
    { sport: 'cycling', minutes: 90 },
  ],
  total_minutes: 290,
  focus: 'threshold',
  key_sessions: [{ sport: 'running', kind: 'long', minutes: 90, detail: '3 x 10 min' }],
  reason: 'Build the base.',
  races: [{ date: '2026-11-22', priority: 'main' }],
};
const WITH_SEASON = altered(WEEKS, [['weeks', 1, 'season'], SEASON]) as typeof WEEKS;
const SEASON_AT = ['weeks', 1, 'season'];

const WRONG_WEEKS: [string, unknown][] = [
  ['no season', altered(WEEKS, [['weeks', 0, 'season'], REMOVE])],
  ['a text as season', altered(WEEKS, [['weeks', 0, 'season'], 'build'])],
  ['an unknown phase', altered(WITH_SEASON, [[...SEASON_AT, 'phase'], 'peak'])],
  ['no recovery flag', altered(WITH_SEASON, [[...SEASON_AT, 'recovery'], REMOVE])],
  ['a fractional aim', altered(WITH_SEASON, [[...SEASON_AT, 'target_minutes'], 1.5])],
  ['an unknown focus', altered(WITH_SEASON, [[...SEASON_AT, 'focus'], 'rest'])],
  ['no reason', altered(WITH_SEASON, [[...SEASON_AT, 'reason'], REMOVE])],
  ['minutes that are no list', altered(WITH_SEASON, [[...SEASON_AT, 'minutes'], {}])],
  [
    'an unknown sport in the minutes',
    altered(WITH_SEASON, [[...SEASON_AT, 'minutes', 0, 'sport'], 'rowing']),
  ],
  [
    'a sport twice in the minutes',
    altered(WITH_SEASON, [[...SEASON_AT, 'minutes', 1, 'sport'], 'running']),
  ],
  ['a total that is not the sum', altered(WITH_SEASON, [[...SEASON_AT, 'total_minutes'], 291])],
  [
    'four key sessions',
    altered(WITH_SEASON, [[...SEASON_AT, 'key_sessions'], Array(4).fill(SEASON.key_sessions[0])]),
  ],
  [
    'an unknown kind of key session',
    altered(WITH_SEASON, [[...SEASON_AT, 'key_sessions', 0, 'kind'], 'party']),
  ],
  ['no races', altered(WITH_SEASON, [[...SEASON_AT, 'races'], REMOVE])],
  [
    'a race without a priority',
    altered(WITH_SEASON, [[...SEASON_AT, 'races', 0, 'priority'], 'x']),
  ],
  ['a race that is no date', altered(WITH_SEASON, [[...SEASON_AT, 'races', 0, 'date'], 'sunday'])],
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

    it('reads the week of the confirmed season plan', async () => {
      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, WITH_SEASON, 200);

      const weeks = (result as { weeks: { season: unknown }[] }).weeks;
      expect(weeks.map((week) => week.season)).toEqual([null, SEASON, null, null, null]);
    });

    it('keeps the texts of the coach as they are, markup included', async () => {
      const text = '<img src=x onerror=alert(1)>';
      const hostile = altered(
        WITH_SEASON,
        [[...SEASON_AT, 'reason'], text],
        [[...SEASON_AT, 'key_sessions', 0, 'detail'], text],
      );

      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, hostile as object, 200);

      const weeks = (result as { weeks: { season: unknown }[] }).weeks;
      expect(weeks[1].season).toMatchObject({
        reason: text,
        key_sessions: [{ detail: text }],
      });
    });

    it('takes over only the known fields of the season week', async () => {
      const crowded = altered(WITH_SEASON, [[...SEASON_AT, 'owner'], 'x']);

      const { result } = await run(api.weeks(), 'GET', WEEKS_URL, crowded as object, 200);

      expect(JSON.stringify(result)).not.toContain('owner');
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

    it('sends the note of the user, as it is', async () => {
      const note = 'No time on Tuesday.\nA trip on Saturday.';

      const { result, request } = await run(
        api.generate('2026-11-16', note),
        'POST',
        URL,
        { ...DRAFT, note },
        201,
      );

      expect(request.request.body).toEqual({ note });
      expect(result).toMatchObject({ kind: 'ok', plan: { note } });
    });

    it.each(['', '   ', '\n\n'])('sends nothing for the note %j', async (note) => {
      const { request } = await run(api.generate('2026-11-16', note), 'POST', URL, DRAFT, 201);

      expect(request.request.body).toEqual({});
    });

    it('says what the server said about a note that does not fit', async () => {
      const { result } = await run(
        api.generate('2026-11-16', 'x'),
        'POST',
        URL,
        { note: ['Use at most 300 characters.'] },
        400,
      );

      expect(result).toEqual({ kind: 'invalid', message: 'Use at most 300 characters.' });
    });

    it.each([null, {}, { note: [] }, { note: [5] }, { note: [''] }, { other: ['x'] }])(
      'has a text of its own when the refusal says nothing usable: %j',
      async (body) => {
        const { result } = await run(api.generate('2026-11-16', 'x'), 'POST', URL, body, 400);

        expect(result).toEqual({
          kind: 'invalid',
          message: 'Your note could not be used. Please check it.',
        });
      },
    );

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

    it.each(['morning', 'afternoon', 'evening'])('knows the time of day %s', async (slot) => {
      const body = altered(DRAFT, [[...WORKOUT, 'slot'], slot]);

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body as object, 201);

      expect(result).toMatchObject({
        plan: { workouts: [{ slot }, { slot: null }, { slot: null }] },
      });
    });

    it('takes over the exercises of a workout in their order', async () => {
      const body = altered(DRAFT, [
        [...WORKOUT, 'exercises'],
        [SQUAT, PLANK],
      ]);

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body as object, 201);

      expect(result).toMatchObject({
        plan: { workouts: [{ exercises: [SQUAT, PLANK] }, { exercises: [] }, { exercises: [] }] },
      });
    });

    it('copies the exercises', async () => {
      const exercises = [{ ...SQUAT }];
      const body = altered(DRAFT, [[...WORKOUT, 'exercises'], exercises]);

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body as object, 201);

      const plan = (result as { plan: { workouts: { exercises: unknown[] }[] } }).plan;
      expect(plan.workouts[0].exercises[0]).not.toBe(exercises[0]);
    });

    it.each([0, 1, 60])('takes over %i minutes of stretching', async (minutes) => {
      const body = altered(DRAFT, [[...WORKOUT, 'stretching_minutes'], minutes]);

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body as object, 201);

      expect(result).toMatchObject({
        plan: { workouts: [{ stretching_minutes: minutes }, {}, {}] },
      });
    });

    it('takes over a day with two workouts at two times', async () => {
      const body = altered(
        DRAFT,
        [[...WORKOUT, 'slot'], 'morning'],
        [['workouts', 1, 'day'], '2026-11-16'],
        [['workouts', 1, 'slot'], 'evening'],
      );

      const { result } = await run(api.generate('2026-11-16'), 'POST', URL, body as object, 201);

      const plan = result.kind === 'ok' ? result.plan : null;
      expect(plan?.workouts.map((w) => [w.day, w.slot])).toEqual([
        ['2026-11-16', 'morning'],
        ['2026-11-16', 'evening'],
        ['2026-11-20', null],
      ]);
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

    it.each([200, 500])('rejects the unexpected status %i', async (status) => {
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

    it('returns the target ranges of workouts and segments', async () => {
      const withTargets = altered(
        DRAFT,
        [[...WORKOUT, 'target'], { low: 138, high: 188, unit: 'W' }],
        [[...SEGMENT, 'target'], { low: 248, high: 300, unit: 'W' }],
      );

      const { result } = await run(api.get(DRAFT_ID), 'GET', URL, withTargets as object, 200);

      expect(result).toMatchObject({ kind: 'ok' });
      const workouts = (result as { plan: WeekPlan }).plan.workouts;
      expect(workouts[0].target).toEqual({ low: 138, high: 188, unit: 'W' });
      expect(workouts[1].target).toBeNull();
      expect(workouts[2].segments[0].target).toEqual({ low: 248, high: 300, unit: 'W' });
      expect(workouts[2].segments[1].target).toBeNull();
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
      expect(result).toEqual({ kind: 'ok', plan: CONFIRMED_DRAFT, push: null });
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

  describe('confirm and send', () => {
    const URL = `/api/planning/plans/${DRAFT_ID}/confirm/`;
    const SENT = {
      ...CONFIRMED_ANSWER(),
      push: { ok: true, synced: 2, failed: 0, removed: 0, left_behind: 0 },
    };

    it('asks for the push only when told to', async () => {
      const { request } = await run(api.confirm(DRAFT_ID, true), 'POST', URL, SENT, 200);

      expect(request.request.body).toEqual({ push: true });
    });

    it('returns what the push did', async () => {
      const { result } = await run(api.confirm(DRAFT_ID, true), 'POST', URL, SENT, 200);

      expect(result).toMatchObject({
        kind: 'ok',
        push: { ok: true, synced: 2, failed: 0, removed: 0, left_behind: 0 },
      });
    });

    it('returns a problem with Intervals.icu as part of the confirmed plan', async () => {
      const problem = {
        ok: false,
        problem: 'not_connected',
        message: 'Intervals.icu is not connected. Connect it on the Connections page.',
      };

      const { result } = await run(
        api.confirm(DRAFT_ID, true),
        'POST',
        URL,
        { ...CONFIRMED_ANSWER(), push: problem },
        200,
      );

      expect(result).toMatchObject({ kind: 'ok', push: problem });
    });

    it('ignores a push result nobody asked for', async () => {
      const { result } = await run(api.confirm(DRAFT_ID), 'POST', URL, SENT, 200);

      expect(result).toMatchObject({ kind: 'ok', push: null });
    });

    it.each([
      ['no result', undefined],
      ['a text as result', 'sent'],
      ['no ok', { synced: 1, failed: 0, removed: 0, left_behind: 0 }],
      ['a negative count', { ok: true, synced: -1, failed: 0, removed: 0, left_behind: 0 }],
      ['a missing count', { ok: true, synced: 1, failed: 0, removed: 0 }],
      ['an unknown problem', { ok: false, problem: 'boom', message: 'x' }],
      ['a problem without text', { ok: false, problem: 'not_connected' }],
    ])('rejects a push with %s', async (_name, push) => {
      await runFailing(
        api.confirm(DRAFT_ID, true),
        'POST',
        URL,
        { ...CONFIRMED_ANSWER(), push } as object,
        200,
      );
    });
  });

  describe('push', () => {
    const URL = `/api/planning/plans/${DRAFT_ID}/push/`;
    const OK = { ok: true, synced: 1, failed: 1, removed: 2, left_behind: 0 };
    const SYNCED = {
      ...CONFIRMED_ANSWER(),
      export: { synced: 1, failed: 1, not_sent: 0, older: 0 },
      push: OK,
    };

    it('posts to the push address and returns the plan with the result', async () => {
      const { result, request } = await run(api.push(DRAFT_ID), 'POST', URL, SYNCED, 200);

      expect(request.request.body).toEqual({});
      expect(result).toMatchObject({
        kind: 'ok',
        push: OK,
        plan: { export: { synced: 1, failed: 1, not_sent: 0, older: 0 } },
      });
    });

    it('reads the export state of every workout', async () => {
      const answer = altered(
        SYNCED,
        [[...WORKOUT, 'export'], exported('failed', 'rejected', SENT_AT)],
        [['workouts', 1, 'export'], exported('synced', '', SENT_AT)],
      );

      const { result } = await run(api.push(DRAFT_ID), 'POST', URL, answer as object, 200);

      const workouts = (result as { plan: WeekPlan }).plan.workouts;
      expect(workouts[0].export).toEqual({
        status: 'failed',
        error_code: 'rejected',
        pushed_at: SENT_AT,
      });
      expect(workouts[1].export).toEqual({ status: 'synced', error_code: '', pushed_at: SENT_AT });
      expect(workouts[2].export).toEqual({ status: 'not_sent', error_code: '', pushed_at: null });
    });

    it.each([
      [409, 'not_confirmed'],
      [409, 'not_connected'],
      [502, 'invalid_key'],
      [502, 'unexpected'],
    ])('tells the problem behind %i %s', async (status, code) => {
      const { result } = await run(
        api.push(DRAFT_ID),
        'POST',
        URL,
        { detail: `Text for ${code}.`, code },
        status,
      );

      expect(result).toEqual({ kind: 'problem', problem: code, message: `Text for ${code}.` });
    });

    it.each([
      [409, 'not_connected'],
      [502, 'unexpected'],
    ])(
      'keeps the meaning of %i if the answer is not from the server (%s)',
      async (status, problem) => {
        const { result } = await run(api.push(DRAFT_ID), 'POST', URL, '<html>nope</html>', status);

        expect(result).toEqual({
          kind: 'problem',
          problem,
          message: 'The week could not be sent to Intervals.icu. Please try again later.',
        });
      },
    );

    it('says when there is no such plan', async () => {
      const { result } = await run(api.push(DRAFT_ID), 'POST', URL, NOT_FOUND, 404);

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('says when too many pushes were made', async () => {
      const { result } = await run(api.push(DRAFT_ID), 'POST', URL, { detail: 'slow down' }, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.push(DRAFT_ID), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('sends nothing for an id that is no uuid', async () => {
      expect(await api.push('12')).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it('rejects an answer without the result of the push', async () => {
      await runFailing(api.push(DRAFT_ID), 'POST', URL, CONFIRMED_ANSWER() as object, 200);
    });

    it.each([400, 422, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.push(DRAFT_ID), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.push(DRAFT_ID), URL);
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

  /** The first workout of the draft as the page sends it back (no `target`, no `export`). */
  function sent(workouts: Workout[] = DRAFT.workouts as Workout[]): EditedPlan {
    return {
      week_start: '2026-11-16',
      rationale: 'Base week with one tempo session.',
      workouts: workouts.map((workout) => ({
        lineage: workout.lineage,
        day: workout.day,
        sport: workout.sport,
        title: workout.title,
        goal: workout.goal,
        duration_minutes: workout.duration_minutes,
        zone_system: workout.zone_system,
        zone: workout.zone,
        notes: workout.notes,
        slot: workout.slot,
        stretching_minutes: workout.stretching_minutes,
        segments: workout.segments.map((segment) => ({
          kind: segment.kind,
          seconds: segment.seconds,
          repeat: segment.repeat,
          zone_system: segment.zone_system,
          zone: segment.zone,
        })),
        exercises: workout.exercises.map((exercise) => ({ ...exercise })),
      })),
    };
  }

  const PROBLEMS = {
    detail: 'The plan cannot be read. Please check the problems.',
    code: 'invalid_plan',
    problems: [{ path: 'workouts[0].lineage', message: 'A lineage is an id or null.' }],
  };
  const NOT_PLANNABLE = { detail: 'This week cannot be planned.', code: 'week_not_plannable' };

  describe('check', () => {
    const URL = '/api/planning/weeks/2026-11-16/check/';
    const ANSWER = { valid: true, findings: [], order: [0, 1, 2] };

    it('posts the plan and returns the report with the order', async () => {
      const { result, request } = await run(
        api.check('2026-11-16', sent()),
        'POST',
        URL,
        ANSWER,
        200,
      );

      expect(request.request.body).toEqual(sent());
      expect(result).toEqual({
        kind: 'ok',
        report: { valid: true, findings: [] },
        order: [0, 1, 2],
      });
    });

    it('returns the findings of a plan with errors', async () => {
      const { result } = await run(
        api.check('2026-11-16', sent()),
        'POST',
        URL,
        {
          valid: false,
          findings: [
            {
              severity: 'error',
              code: 'day_over_capacity',
              message: 'Too long for this day.',
              path: 'workouts[1]',
            },
          ],
          order: [2, 0, 1],
        },
        200,
      );

      expect(result).toEqual({
        kind: 'ok',
        report: {
          valid: false,
          findings: [
            {
              severity: 'error',
              code: 'day_over_capacity',
              message: 'Too long for this day.',
              path: 'workouts[1]',
            },
          ],
        },
        order: [2, 0, 1],
      });
    });

    it('sends only the fields of the format, never the target or the export', async () => {
      const crowded = (DRAFT.workouts as Workout[]).map((workout) => ({
        ...workout,
        target: { low: 1, high: 2, unit: 'W' as const },
        export: {
          status: 'synced' as const,
          error_code: '' as const,
          pushed_at: '2026-11-14T08:00:00Z',
        },
        segments: workout.segments.map((segment) => ({
          ...segment,
          target: { low: 1, high: 2, unit: 'W' as const },
        })),
      }));

      const { request } = await run(
        api.check('2026-11-16', { ...sent(), workouts: crowded }),
        'POST',
        URL,
        ANSWER,
        200,
      );

      expect(request.request.body).toEqual(sent());
      expect(JSON.stringify(request.request.body)).not.toContain('target');
      expect(JSON.stringify(request.request.body)).not.toContain('export');
    });

    it('sends the exercises as they are and nothing else of them', async () => {
      const plan = sent();
      const exercises = [
        { ...SQUAT, region: 'legs' as const, equipment: 'dumbbells' as const },
        { ...PLANK, region: 'core' as const, equipment: 'bodyweight' as const },
      ];
      plan.workouts[0] = {
        ...plan.workouts[0],
        exercises: exercises.map((exercise) => ({ ...exercise, extra: 'x' })),
      };

      const { request } = await run(api.check('2026-11-16', plan), 'POST', URL, ANSWER, 200);

      expect((request.request.body as EditedPlan).workouts[0].exercises).toEqual(exercises);
    });

    it('sends a new workout with a null lineage', async () => {
      const plan = sent();
      plan.workouts[1] = { ...plan.workouts[1], lineage: null };

      const { request } = await run(api.check('2026-11-16', plan), 'POST', URL, ANSWER, 200);

      expect((request.request.body as EditedPlan).workouts[1].lineage).toBeNull();
    });

    it('sends nothing for a week that is no date', async () => {
      expect(await api.check('../x', sent())).toEqual({ kind: 'not_plannable' });
      expect(await api.check('2026-02-30', sent())).toEqual({ kind: 'not_plannable' });
      backend.expectNone(() => true);
    });

    it('says when the week cannot be planned', async () => {
      const { result } = await run(
        api.check('2026-11-16', sent()),
        'POST',
        URL,
        NOT_PLANNABLE,
        404,
      );

      expect(result).toEqual({ kind: 'not_plannable' });
    });

    it('returns what was wrong with the plan', async () => {
      const { result } = await run(api.check('2026-11-16', sent()), 'POST', URL, PROBLEMS, 422);

      expect(result).toEqual({
        kind: 'invalid',
        problems: [{ path: 'workouts[0].lineage', message: 'A lineage is an id or null.' }],
      });
    });

    it('says when the session is gone', async () => {
      for (const status of [401, 403]) {
        const { result } = await run(
          api.check('2026-11-16', sent()),
          'POST',
          URL,
          NO_SESSION,
          status,
        );
        expect(result).toEqual({ kind: 'forbidden' });
      }
    });

    it.each([
      ['no order', { valid: true, findings: [] }],
      ['an order of the wrong length', { valid: true, findings: [], order: [0, 1] }],
      ['an order with a place twice', { valid: true, findings: [], order: [0, 0, 1] }],
      ['an order with a place that is not there', { valid: true, findings: [], order: [0, 1, 3] }],
      ['an order of texts', { valid: true, findings: [], order: ['0', '1', '2'] }],
      ['an order with a fraction', { valid: true, findings: [], order: [0, 1, 1.5] }],
      ['a negative place', { valid: true, findings: [], order: [0, 1, -1] }],
      [
        'a verdict that does not fit the findings',
        {
          valid: true,
          findings: [{ severity: 'error', code: 'x', message: 'm', path: '' }],
          order: [0, 1, 2],
        },
      ],
      ['no report', { order: [0, 1, 2] }],
    ])('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.check('2026-11-16', sent()), 'POST', URL, bad, 200);
    });

    it.each([400, 409, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.check('2026-11-16', sent()), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.check('2026-11-16', sent()), URL);
    });

    it('rejects problems of the wrong shape', async () => {
      await runFailing(api.check('2026-11-16', sent()), 'POST', URL, { problems: 'x' }, 422);
      await runFailing(
        api.check('2026-11-16', sent()),
        'POST',
        URL,
        { problems: [{ path: 1 }] },
        422,
      );
    });
  });

  describe('revise', () => {
    const URL = `/api/planning/plans/${CONFIRMED_ID}/revise/`;
    const NEW_DRAFT = { ...DRAFT, version: 2, parent: CONFIRMED_ID, reason: 'Changed by hand' };

    it('posts the plan and returns the new draft with its checks', async () => {
      const { result, request } = await run(
        api.revise(CONFIRMED_ID, sent()),
        'POST',
        URL,
        NEW_DRAFT,
        201,
      );

      expect(request.request.body).toEqual(sent());
      expect(result).toEqual({ kind: 'ok', plan: NEW_DRAFT as WeekPlan });
    });

    it('sends nothing for an id that is no uuid', async () => {
      expect(await api.revise('../x', sent())).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it('tells a plan that does not exist from a week that cannot be planned', async () => {
      const gone = await run(api.revise(CONFIRMED_ID, sent()), 'POST', URL, NOT_FOUND, 404);
      const week = await run(api.revise(CONFIRMED_ID, sent()), 'POST', URL, NOT_PLANNABLE, 404);
      const other = await run(api.revise(CONFIRMED_ID, sent()), 'POST', URL, '<html>', 404);

      expect(gone.result).toEqual({ kind: 'not_found' });
      expect(week.result).toEqual({ kind: 'not_plannable' });
      expect(other.result).toEqual({ kind: 'not_found' });
    });

    it('says when the plan cannot be changed', async () => {
      const { result } = await run(
        api.revise(CONFIRMED_ID, sent()),
        'POST',
        URL,
        { detail: 'Only a draft or a confirmed plan can be changed.', code: 'not_revisable' },
        409,
      );

      expect(result).toEqual({ kind: 'not_revisable' });
    });

    it('returns what was wrong with the plan', async () => {
      const { result } = await run(api.revise(CONFIRMED_ID, sent()), 'POST', URL, PROBLEMS, 422);

      expect(result).toEqual({
        kind: 'invalid',
        problems: [{ path: 'workouts[0].lineage', message: 'A lineage is an id or null.' }],
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(
        api.revise(CONFIRMED_ID, sent()),
        'POST',
        URL,
        NO_SESSION,
        status,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects a stored plan with %s', async (_name, bad) => {
      await runFailing(api.revise(CONFIRMED_ID, sent()), 'POST', URL, bad as object | null, 201);
    });

    it('rejects a draft without its checks', async () => {
      await runFailing(
        api.revise(CONFIRMED_ID, sent()),
        'POST',
        URL,
        { ...NEW_DRAFT, report: null },
        201,
      );
    });

    it.each([400, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.revise(CONFIRMED_ID, sent()), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.revise(CONFIRMED_ID, sent()), URL);
    });
  });

  describe('restore', () => {
    const URL = `/api/planning/plans/${CONFIRMED_ID}/restore/`;
    const RESTORED = {
      ...DRAFT,
      version: 3,
      parent: CONFIRMED_ID,
      reason: 'Restored from version 1',
    };

    it('posts to the restore address and returns the new draft', async () => {
      const { result, request } = await run(api.restore(CONFIRMED_ID), 'POST', URL, RESTORED, 201);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', plan: RESTORED as WeekPlan });
    });

    it('sends nothing for an id that is no uuid', async () => {
      expect(await api.restore('../x')).toEqual({ kind: 'not_found' });
      backend.expectNone(() => true);
    });

    it('tells a plan that does not exist from a week that cannot be planned', async () => {
      const gone = await run(api.restore(CONFIRMED_ID), 'POST', URL, NOT_FOUND, 404);
      const week = await run(api.restore(CONFIRMED_ID), 'POST', URL, NOT_PLANNABLE, 404);

      expect(gone.result).toEqual({ kind: 'not_found' });
      expect(week.result).toEqual({ kind: 'not_plannable' });
    });

    it('says when the version cannot be restored', async () => {
      const { result } = await run(
        api.restore(CONFIRMED_ID),
        'POST',
        URL,
        {
          detail: 'Only a version that was replaced or discarded can be restored.',
          code: 'not_restorable',
        },
        409,
      );

      expect(result).toEqual({ kind: 'not_restorable' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.restore(CONFIRMED_ID), 'POST', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_PLANS)('rejects a stored plan with %s', async (_name, bad) => {
      await runFailing(api.restore(CONFIRMED_ID), 'POST', URL, bad as object | null, 201);
    });

    it.each([400, 422, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.restore(CONFIRMED_ID), 'POST', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      await failsOnTheNetwork(api.restore(CONFIRMED_ID), URL);
    });
  });
});
