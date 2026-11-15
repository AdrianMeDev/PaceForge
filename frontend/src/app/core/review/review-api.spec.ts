import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { ReviewApi } from './review-api';
import { CorrectionInput, FeedbackInput } from './review-models';

const BASE = '/api/reviews/weeks/';
const WEEK = '2026-11-09';
const WORKOUT = '01a1dbcf-cb4a-74c1-9813-f266175f1111';
const ACTIVITY = '01a1dbcf-cb4a-74c1-9813-f266175f2222';

// The shapes are those of the real API (see reviews/serializers.py).
const FIGURES = {
  planned_count: 2,
  planned_minutes: 120,
  actual_count: 1,
  actual_minutes: 60,
  load: 360,
  rated_count: 1,
};
const REVIEW = {
  week_start: WEEK,
  today: '2026-11-14',
  plan: {
    id: '01a1dbcf-cb4a-74c1-9813-f266175f3333',
    version: 2,
    confirmed_at: '2026-11-08T18:00:00Z',
  },
  workouts: [
    {
      id: WORKOUT,
      day: WEEK,
      position: 0,
      sport: 'running',
      title: 'Easy run',
      goal: 'endurance',
      duration_minutes: 60,
      slot: 'morning',
      notes: 'Keep it easy',
      status: 'done',
      status_origin: 'auto',
      activity_id: ACTIVITY,
      activity_origin: 'auto',
    },
    {
      id: '01a1dbcf-cb4a-74c1-9813-f266175f4444',
      day: '2026-11-10',
      position: 0,
      sport: 'cycling',
      title: 'Ride',
      goal: 'tempo',
      duration_minutes: 60,
      slot: null,
      notes: '',
      status: 'missed',
      status_origin: 'user',
      activity_id: null,
      activity_origin: 'user',
    },
  ],
  activities: [
    {
      id: ACTIVITY,
      source: 'manual',
      sport: 'running',
      start_time: '2026-11-09T07:00:00Z',
      day: WEEK,
      elapsed_seconds: null,
      timer_seconds: 3600,
      distance_m: null,
      rpe: 6,
      notes: 'felt good',
      load: 360,
      workout_id: WORKOUT,
    },
  ],
  comparison: {
    sports: [
      { sport: 'running', ...FIGURES },
      { sport: 'cycling', ...FIGURES, actual_count: 0, actual_minutes: 0, load: 0, rated_count: 0 },
    ],
    total: FIGURES,
    statuses: { done: 1, partial: 0, missed: 1, replaced: 0, open: 0 },
    done_percent: 50,
  },
  feedback: {
    fatigue: 4,
    motivation: null,
    pain: 1,
    notes: 'Heavy legs',
    updated_at: '2026-11-14T08:00:00.123456Z',
  },
  comment: null,
};
const WEEKS = {
  weeks: [
    { week_start: '2026-11-02', has_plan: false, workout_count: 0, has_feedback: true },
    { week_start: WEEK, has_plan: true, workout_count: 2, has_feedback: false },
  ],
};
const NO_SESSION = { detail: 'Authentication credentials were not provided.' };

describe('ReviewApi', () => {
  let api: ReviewApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ReviewApi);
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

  /** A copy of the week with one change, written the way a path says it. */
  function changed(change: (review: typeof REVIEW) => void): object {
    const copy = structuredClone(REVIEW);
    change(copy);
    return copy;
  }

  describe('weeks', () => {
    it('returns the weeks that can be reviewed', async () => {
      const { result } = await run(api.weeks(), 'GET', BASE, WEEKS, 200);

      expect(result).toEqual({ kind: 'ok', weeks: WEEKS.weeks });
    });

    it('takes over only the known fields', async () => {
      const { result } = await run(
        api.weeks(),
        'GET',
        BASE,
        { weeks: [{ ...WEEKS.weeks[1], owner: 7, secret: 'x' }], extra: true },
        200,
      );

      expect(result).toEqual({ kind: 'ok', weeks: [WEEKS.weeks[1]] });
    });

    it('says when the session has ended', async () => {
      for (const status of [401, 403]) {
        const { result } = await run(api.weeks(), 'GET', BASE, NO_SESSION, status);
        expect(result).toEqual({ kind: 'forbidden' });
      }
    });

    it.each([
      ['no list', { weeks: 'x' }],
      ['a date that is none', { weeks: [{ ...WEEKS.weeks[0], week_start: 'Monday' }] }],
      ['a flag that is none', { weeks: [{ ...WEEKS.weeks[0], has_plan: 'yes' }] }],
      ['a negative count', { weeks: [{ ...WEEKS.weeks[0], workout_count: -1 }] }],
      ['a fraction as a count', { weeks: [{ ...WEEKS.weeks[0], workout_count: 1.5 }] }],
      ['no object', { weeks: [5] }],
    ])('rejects an answer of the wrong shape: %s', async (_, body) => {
      await runFailing(api.weeks(), 'GET', BASE, body, 200);
    });

    it('rejects a server error', async () => {
      await runFailing(api.weeks(), 'GET', BASE, null, 500);
    });
  });

  describe('week', () => {
    it('returns the week with everything the page shows', async () => {
      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, REVIEW, 200);

      expect(result).toEqual({ kind: 'ok', review: REVIEW });
    });

    it('returns a week without a plan, without feedback and without any activity', async () => {
      const bare = changed((review) => {
        Object.assign(review, { plan: null, workouts: [], activities: [], feedback: null });
        review.comparison.sports = [];
        review.comparison.done_percent = null as unknown as number;
      });

      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, bare, 200);

      expect(result).toEqual({
        kind: 'ok',
        review: expect.objectContaining({
          plan: null,
          workouts: [],
          activities: [],
          feedback: null,
        }),
      });
    });

    it('reads what is missing as null', async () => {
      const sparse = changed((review) => {
        review.plan.confirmed_at = null as unknown as string;
        review.activities[0].rpe = null as unknown as number;
        review.activities[0].load = null as unknown as number;
        review.feedback.fatigue = null as unknown as number;
      });

      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, sparse, 200);

      expect(result.kind === 'ok' && result.review.plan?.confirmed_at).toBeNull();
      expect(result.kind === 'ok' && result.review.activities[0].load).toBeNull();
      expect(result.kind === 'ok' && result.review.feedback?.fatigue).toBeNull();
    });

    it('returns the comment of the coach', async () => {
      const commented = changed((review) => {
        Object.assign(review, {
          comment: {
            comment: 'A <b>steady</b> week.\nKeep it up.',
            next_week: 'hold',
            created_at: '2026-11-14T09:30:00Z',
            owner: 7,
          },
        });
      });

      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, commented, 200);

      expect(result.kind === 'ok' && result.review.comment).toEqual({
        comment: 'A <b>steady</b> week.\nKeep it up.',
        next_week: 'hold',
        created_at: '2026-11-14T09:30:00Z',
      });
    });

    it.each([
      ['an unknown recommendation', { next_week: 'maintain' }],
      ['an empty comment', { comment: '' }],
      ['a comment that is no text', { comment: 5 }],
      ['no time', { created_at: '' }],
    ])('rejects a comment of the wrong shape: %s', async (_, change) => {
      const broken = changed((review) => {
        Object.assign(review, {
          comment: {
            comment: 'Fine.',
            next_week: 'hold',
            created_at: '2026-11-14T09:30:00Z',
            ...change,
          },
        });
      });

      await runFailing(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, broken, 200);
    });

    it('rejects an answer without the comment field', async () => {
      const old = changed((review) => delete (review as { comment?: unknown }).comment);

      await runFailing(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, old, 200);
    });

    it('takes over only the known fields', async () => {
      const crowded = changed((review) => {
        Object.assign(review, { owner: 7 });
        Object.assign(review.workouts[0], { source_hash: 'x' });
        Object.assign(review.activities[0], { laps: [1], source_hash: 'x' });
        Object.assign(review.comparison.total, { tss: 9 });
      });

      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, crowded, 200);

      expect(result).toEqual({ kind: 'ok', review: REVIEW });
    });

    it('does not even ask for something that is no date', async () => {
      for (const week of ['', 'Monday', '2026-11-9', '../planning', '2026-11-09/x']) {
        expect(await api.week(week)).toEqual({ kind: 'not_reviewable' });
      }
    });

    it('says when the week cannot be reviewed', async () => {
      const { result } = await run(
        api.week('2026-02-02'),
        'GET',
        `${BASE}2026-02-02/`,
        { detail: 'This week cannot be reviewed.', code: 'week_not_reviewable' },
        404,
      );

      expect(result).toEqual({ kind: 'not_reviewable' });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each<[string, (review: typeof REVIEW) => void]>([
      ['an unknown status', (r) => ((r.workouts[0] as { status: string }).status = 'skipped')],
      [
        'a sport a plan has no word for',
        (r) => ((r.workouts[0] as { sport: string }).sport = 'other'),
      ],
      [
        'an unknown origin',
        (r) => ((r.workouts[0] as { status_origin: string }).status_origin = 'bot'),
      ],
      ['an unknown source', (r) => ((r.activities[0] as { source: string }).source = 'strava')],
      ['no id', (r) => ((r.workouts[0] as { id: unknown }).id = '')],
      ['a day that is none', (r) => ((r.workouts[0] as { day: string }).day = 'Mon')],
      ['a position that is none', (r) => ((r.workouts[0] as { position: unknown }).position = '0')],
      ['a rpe that is text', (r) => ((r.activities[0] as { rpe: unknown }).rpe = '6')],
      ['a rpe that is not finite', (r) => ((r.activities[0] as { rpe: unknown }).rpe = Infinity)],
      ['a note that is not text', (r) => ((r.activities[0] as { notes: unknown }).notes = 5)],
      ['missing statuses', (r) => delete (r.comparison.statuses as { open?: number }).open],
      [
        'a share that is text',
        (r) => ((r.comparison as { done_percent: unknown }).done_percent = '50'),
      ],
      ['no workouts list', (r) => ((r as { workouts: unknown }).workouts = {})],
      ['no comparison', (r) => ((r as { comparison: unknown }).comparison = null)],
      ['feedback that is a list', (r) => ((r as { feedback: unknown }).feedback = [])],
    ])('rejects an answer of the wrong shape: %s', async (_, change) => {
      await runFailing(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, changed(change), 200);
    });

    it('rejects a server error and a network failure', async () => {
      await runFailing(api.week(WEEK), 'GET', `${BASE}${WEEK}/`, null, 500);

      const action = api.week(WEEK);
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne(`${BASE}${WEEK}/`));
      request.error(new ProgressEvent('error'));
      await expect(action).rejects.toBeTruthy();
    });
  });

  describe('correct', () => {
    const URL = `${BASE}${WEEK}/workouts/${WORKOUT}/`;
    const INPUT: CorrectionInput = { activity: ACTIVITY, no_activity: false, status: 'partial' };

    it('puts the decision as JSON and returns the whole week', async () => {
      const { result, request } = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        REVIEW,
        200,
      );

      expect(request.request.body).toEqual(INPUT);
      expect(result).toEqual({ kind: 'ok', review: REVIEW });
    });

    it('sends an empty decision as it is: back to the automatic match', async () => {
      const empty: CorrectionInput = { activity: null, no_activity: false, status: '' };

      const { request } = await run(api.correct(WEEK, WORKOUT, empty), 'PUT', URL, REVIEW, 200);

      expect(request.request.body).toEqual(empty);
    });

    it('writes the workout id safely into the address', async () => {
      const action = api.correct(WEEK, 'a/b?c', INPUT);
      action.catch(() => undefined);

      const request = await vi.waitFor(() =>
        backend.expectOne(`${BASE}${WEEK}/workouts/a%2Fb%3Fc/`),
      );
      request.flush(null, { status: 404, statusText: 'Not Found' });
      await action;
    });

    it('does not even send a week that is no date', async () => {
      expect(await api.correct('nonsense', WORKOUT, INPUT)).toEqual({ kind: 'not_reviewable' });
    });

    it('returns the messages by field and drops everything else', async () => {
      const { result } = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        {
          status: ['This status needs an activity. Link one first.'],
          activity: ['Choose an activity of this week.', 5, ''],
          owner: ['x'],
          non_field_errors: ['ignored while a field has a message'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: {
          status: ['This status needs an activity. Link one first.'],
          activity: ['Choose an activity of this week.'],
        },
        message: null,
      });
    });

    it('returns the general message when no field is named', async () => {
      const { result } = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        { non_field_errors: ['Only the fields of this form can be sent.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: {},
        message: 'Only the fields of this form can be sent.',
      });
    });

    it('has a text of its own when the refusal says nothing usable', async () => {
      const { result } = await run(api.correct(WEEK, WORKOUT, INPUT), 'PUT', URL, 'oops', 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: {},
        message: 'Your entries could not be saved. Please check them.',
      });
    });

    it('tells the workout that is not there from the week that cannot be reviewed', async () => {
      const gone = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        { detail: 'There is no such workout in this week.', code: 'workout_not_found' },
        404,
      );
      const week = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        { detail: 'This week cannot be reviewed.', code: 'week_not_reviewable' },
        404,
      );
      const other = await run(api.correct(WEEK, WORKOUT, INPUT), 'PUT', URL, '<html>', 404);

      expect(gone.result).toEqual({ kind: 'workout_not_found' });
      expect(week.result).toEqual({ kind: 'not_reviewable' });
      expect(other.result).toEqual({ kind: 'not_reviewable' });
    });

    it('says when the activity is assigned to another workout', async () => {
      const { result } = await run(
        api.correct(WEEK, WORKOUT, INPUT),
        'PUT',
        URL,
        { detail: 'This activity is already assigned to another workout.', code: 'activity_taken' },
        409,
      );

      expect(result).toEqual({ kind: 'activity_taken' });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.correct(WEEK, WORKOUT, INPUT), 'PUT', URL, NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape and a server error', async () => {
      await runFailing(api.correct(WEEK, WORKOUT, INPUT), 'PUT', URL, { week_start: WEEK }, 200);
      await runFailing(api.correct(WEEK, WORKOUT, INPUT), 'PUT', URL, null, 500);
    });
  });

  describe('saveFeedback', () => {
    const URL = `${BASE}${WEEK}/feedback/`;
    const INPUT: FeedbackInput = { fatigue: 4, motivation: null, pain: 1, notes: 'Heavy legs' };

    it('puts the feedback as JSON and returns the whole week', async () => {
      const { result, request } = await run(api.saveFeedback(WEEK, INPUT), 'PUT', URL, REVIEW, 200);

      expect(request.request.body).toEqual(INPUT);
      expect(result).toEqual({ kind: 'ok', review: REVIEW });
    });

    it('does not even send a week that is no date', async () => {
      expect(await api.saveFeedback('nonsense', INPUT)).toEqual({ kind: 'not_reviewable' });
    });

    it('returns the messages by field and drops everything else', async () => {
      const { result } = await run(
        api.saveFeedback(WEEK, INPUT),
        'PUT',
        URL,
        {
          fatigue: ['Ensure this value is less than or equal to 5.'],
          notes: ['Must not contain control characters.'],
          week_start: ['x'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: {
          fatigue: ['Ensure this value is less than or equal to 5.'],
          notes: ['Must not contain control characters.'],
        },
        message: null,
      });
    });

    it('has a text of its own when the refusal says nothing usable', async () => {
      const { result } = await run(api.saveFeedback(WEEK, INPUT), 'PUT', URL, null, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: {},
        message: 'Your entries could not be saved. Please check them.',
      });
    });

    it('says when the week cannot be reviewed or the session has ended', async () => {
      const week = await run(api.saveFeedback(WEEK, INPUT), 'PUT', URL, null, 404);
      const out = await run(api.saveFeedback(WEEK, INPUT), 'PUT', URL, NO_SESSION, 401);

      expect(week.result).toEqual({ kind: 'not_reviewable' });
      expect(out.result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape and a server error', async () => {
      await runFailing(api.saveFeedback(WEEK, INPUT), 'PUT', URL, [], 200);
      await runFailing(api.saveFeedback(WEEK, INPUT), 'PUT', URL, null, 503);
    });
  });

  describe('askCoach', () => {
    const URL = `${BASE}${WEEK}/comment/`;
    const COMMENTED = {
      ...REVIEW,
      comment: {
        comment: 'One of two done.',
        next_week: 'reduce',
        created_at: '2026-11-15T08:00:00Z',
      },
    };

    it('posts and returns the whole week with the comment', async () => {
      const { result, request } = await run(api.askCoach(WEEK), 'POST', URL, COMMENTED, 201);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', review: COMMENTED });
    });

    it('does not even send something that is no date', async () => {
      for (const week of ['', 'Monday', '2026-11-9', '../planning']) {
        expect(await api.askCoach(week)).toEqual({ kind: 'not_reviewable' });
      }
    });

    it('says when the week cannot be reviewed', async () => {
      const { result } = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { detail: 'This week cannot be reviewed.', code: 'week_not_reviewable' },
        404,
      );

      expect(result).toEqual({ kind: 'not_reviewable' });
    });

    it('tells the two conflicts apart', async () => {
      const nothing = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { detail: 'There is nothing to look back on in this week yet.', code: 'nothing_to_review' },
        409,
      );
      const none = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { detail: 'No AI provider is set up.', code: 'not_configured' },
        409,
      );

      expect(nothing.result).toEqual({ kind: 'nothing_to_review' });
      expect(none.result).toEqual({ kind: 'not_configured' });
    });

    it('rejects a conflict that is none of the two', async () => {
      await runFailing(api.askCoach(WEEK), 'POST', URL, { code: 'other' }, 409);
      await runFailing(api.askCoach(WEEK), 'POST', URL, '<html>', 409);
    });

    it('returns what was wrong with an answer that could not be used', async () => {
      const { result } = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        {
          detail: 'The coach did not give a comment that can be used. Please try again.',
          code: 'not_usable',
          problems: [{ path: 'next_week', message: 'Use one of "increase", "hold", "reduce".' }],
          extra: 'x',
        },
        422,
      );

      expect(result).toEqual({
        kind: 'not_usable',
        problems: [{ path: 'next_week', message: 'Use one of "increase", "hold", "reduce".' }],
      });
    });

    it('rejects problems of the wrong shape', async () => {
      await runFailing(api.askCoach(WEEK), 'POST', URL, { problems: 'x' }, 422);
      await runFailing(api.askCoach(WEEK), 'POST', URL, { problems: [{ path: 1 }] }, 422);
      await runFailing(api.askCoach(WEEK), 'POST', URL, 'oops', 422);
    });

    it.each([
      [502, 'invalid_key', 'The provider did not accept the key.', null],
      [502, 'not_allowed', 'This address is no longer allowed on this server.', null],
      [503, 'unavailable', 'The provider cannot be reached right now.', null],
      [502, 'unexpected', 'The provider answered in an unexpected way.', null],
    ])('returns a provider problem (%i %s)', async (status, code, detail, retry) => {
      const { result } = await run(api.askCoach(WEEK), 'POST', URL, { code, detail }, status);

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: code,
        message: detail,
        retry_after: retry,
      });
    });

    it('says how long to wait when the provider asks to slow down', async () => {
      const { result } = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { code: 'rate_limited', detail: 'The provider is asking to slow down.', retry_after: 17 },
        429,
      );

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider is asking to slow down.',
        retry_after: 17,
      });
    });

    it('tells the limit of this server from the limit of the provider', async () => {
      const { result } = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { detail: 'Request was throttled. Expected available in 60 seconds.' },
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('uses a text of its own when a proxy answers instead of the server', async () => {
      const bad = await run(api.askCoach(WEEK), 'POST', URL, '<html>Bad gateway</html>', 502);
      const down = await run(api.askCoach(WEEK), 'POST', URL, '<html>Down</html>', 503);

      expect(bad.result).toEqual({
        kind: 'provider_problem',
        problem: 'unexpected',
        message: 'The AI provider could not be used right now. Please try again later.',
        retry_after: null,
      });
      expect(down.result).toMatchObject({ problem: 'unavailable', retry_after: null });
    });

    it('ignores a retry time that is no whole number', async () => {
      const { result } = await run(
        api.askCoach(WEEK),
        'POST',
        URL,
        { code: 'rate_limited', detail: 'Slow down.', retry_after: -3 },
        429,
      );

      expect(result).toMatchObject({ retry_after: null });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.askCoach(WEEK), 'POST', URL, NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape and a server error', async () => {
      await runFailing(api.askCoach(WEEK), 'POST', URL, { week_start: WEEK }, 201);
      await runFailing(api.askCoach(WEEK), 'POST', URL, null, 500);
    });
  });
});
