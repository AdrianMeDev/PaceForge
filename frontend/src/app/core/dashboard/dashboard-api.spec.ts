import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { DashboardApi } from './dashboard-api';

const URL = '/api/dashboard/';
const WEEK = '2026-11-09';

// The shapes are those of the real API (see dashboard/serializers.py).
const EMPTY = {
  week: {
    week_start: WEEK,
    next_workout: null,
    figures: {
      planned_minutes: 0,
      done_minutes: 0,
      workouts_done: 0,
      workouts_total: 0,
      average_rpe: null,
    },
    close_week: null,
  },
  season: null,
  main_goal: null,
  weeks: [{ week_start: WEEK, sports: [] }],
  recent: [],
  usage: { calls: 0, input_tokens: 0, output_tokens: 0, days: 30 },
  setup: { steps: [] },
};

const FULL = {
  week: {
    week_start: WEEK,
    next_workout: {
      id: '01a1dbcf-cb4a-74c1-9813-f266175f1111',
      day: '2026-11-14',
      sport: 'running',
      title: 'Easy run',
      minutes: 60,
      zone_system: 'heart_rate',
      zone: 2,
      sent: true,
    },
    figures: {
      planned_minutes: 240,
      done_minutes: 150,
      workouts_done: 2,
      workouts_total: 4,
      average_rpe: 5.5,
    },
    close_week: '2026-11-02',
  },
  season: { phase: 'build', recovery: false, target_minutes: 300 },
  main_goal: {
    id: '01a1dbcf-cb4a-74c1-9813-f266175f2222',
    title: 'My 10k',
    kind: 'race',
    target_date: '2027-01-02',
    weeks_left: 7,
    assessment: { rating: 'ambitious', reason: null, extra: 1 },
  },
  weeks: [
    {
      week_start: WEEK,
      sports: [
        { sport: 'running', minutes: 90 },
        { sport: 'other', minutes: 60 },
      ],
    },
  ],
  recent: [
    {
      id: '01a1dbcf-cb4a-74c1-9813-f266175f3333',
      day: '2026-11-10',
      sport: 'cycling',
      minutes: null,
    },
  ],
  usage: { calls: 3, input_tokens: 1200, output_tokens: 300, days: 30 },
  setup: {
    steps: [
      { key: 'profile', done: true, optional: false },
      { key: 'intervals', done: false, optional: true },
    ],
  },
};

describe('DashboardApi', () => {
  let api: DashboardApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(DashboardApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function answer(reply: object | null, status = 200) {
    const result = api.get();
    const request = await vi.waitFor(() => backend.expectOne(URL));
    expect(request.request.method).toBe('GET');
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return result;
  }

  async function refuses(reply: object | null) {
    const result = api.get().then(
      () => 'resolved',
      () => 'rejected',
    );
    const request = await vi.waitFor(() => backend.expectOne(URL));
    request.flush(reply);
    expect(await result).toBe('rejected');
  }

  function changed(change: (copy: typeof FULL) => void): object {
    const copy = structuredClone(FULL);
    change(copy);
    return copy;
  }

  it('reads an account that has nothing yet', async () => {
    expect(await answer(EMPTY)).toEqual({ kind: 'ok', dashboard: { ...EMPTY, setup: [] } });
  });

  it('reads a full answer and takes over only the rating of the goal', async () => {
    const result = await answer(FULL);

    expect(result.kind).toBe('ok');
    if (result.kind !== 'ok') {
      return;
    }
    expect(result.dashboard.week.next_workout).toEqual(FULL.week.next_workout);
    expect(result.dashboard.week.close_week).toBe('2026-11-02');
    expect(result.dashboard.season).toEqual(FULL.season);
    expect(result.dashboard.main_goal).toEqual({
      id: FULL.main_goal.id,
      title: 'My 10k',
      kind: 'race',
      target_date: '2027-01-02',
      weeks_left: 7,
      rating: 'ambitious',
    });
    expect(result.dashboard.weeks[0].sports).toHaveLength(2);
    expect(result.dashboard.recent[0].minutes).toBeNull();
    expect(result.dashboard.usage.calls).toBe(3);
    expect(result.dashboard.setup).toEqual([
      { key: 'profile', done: true, optional: false },
      { key: 'intervals', done: false, optional: true },
    ]);
  });

  it('reads no zone as null', async () => {
    const result = await answer(
      changed((copy) => {
        Object.assign(copy.week.next_workout, { zone_system: '', zone: null });
      }),
    );

    expect(result.kind === 'ok' && result.dashboard.week.next_workout?.zone_system).toBeNull();
  });

  it('says forbidden for 401 and 403', async () => {
    expect(await answer({}, 403)).toEqual({ kind: 'forbidden' });
    expect(await answer({}, 401)).toEqual({ kind: 'forbidden' });
  });

  it('rejects a server error', async () => {
    const result = api.get().then(
      () => 'resolved',
      () => 'rejected',
    );
    const request = await vi.waitFor(() => backend.expectOne(URL));
    request.flush('', { status: 500, statusText: 'Server Error' });
    expect(await result).toBe('rejected');
  });

  it.each([
    ['a body that is no object', null],
    ['a missing week', { ...EMPTY, week: undefined }],
    ['weeks that are no list', { ...EMPTY, weeks: {} }],
    ['an unknown sport', changed((c) => (c.weeks[0].sports[0].sport = 'golf'))],
    ['an unknown phase', changed((c) => (c.season.phase = 'summer'))],
    ['an unknown rating', changed((c) => (c.main_goal.assessment.rating = 'easy'))],
    [
      'a goal without an assessment',
      changed((c) => Object.assign(c.main_goal, { assessment: null })),
    ],
    ['a date that is none', changed((c) => (c.week.week_start = 'Monday'))],
    ['negative minutes', changed((c) => (c.week.figures.done_minutes = -1))],
    ['fractional minutes', changed((c) => (c.week.figures.planned_minutes = 1.5))],
    [
      'a rating that is no number',
      changed((c) => Object.assign(c.week.figures, { average_rpe: '5' })),
    ],
    [
      'a zone without a system',
      changed((c) => Object.assign(c.week.next_workout, { zone_system: '' })),
    ],
    [
      'a sent flag that is no boolean',
      changed((c) => Object.assign(c.week.next_workout, { sent: 1 })),
    ],
    ['weeks left below zero', changed((c) => (c.main_goal.weeks_left = -1))],
    ['an empty title', changed((c) => (c.main_goal.title = ''))],
    ['usage that is missing', { ...EMPTY, usage: null }],
    ['setup that is missing', { ...EMPTY, setup: null }],
    ['setup steps that are no list', { ...EMPTY, setup: { steps: 'profile' } }],
    [
      'a setup step that is not known',
      { ...EMPTY, setup: { steps: [{ key: 'tour', done: true, optional: false }] } },
    ],
    [
      'a setup step without a done flag',
      { ...EMPTY, setup: { steps: [{ key: 'goal', done: 'yes', optional: false }] } },
    ],
  ])('rejects %s', async (_name, reply) => {
    await refuses(reply);
  });
});
