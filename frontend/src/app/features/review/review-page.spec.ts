import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { ActivitiesApi } from '../../core/activities/activities-api';
import { RateActivityResult } from '../../core/activities/activities-models';
import { PlanningApi } from '../../core/planning/planning-api';
import { GenerateResult } from '../../core/planning/planning-models';
import { ReviewApi } from '../../core/review/review-api';
import {
  AskCoachResult,
  CorrectResult,
  GetReviewResult,
  ListReviewWeeksResult,
  ReviewActivity,
  ReviewWorkout,
  SaveFeedbackResult,
  ReviewableWeek,
  WeekReview,
} from '../../core/review/review-models';
import { query, settle } from '../../testing/dom';
import { ReviewPage } from './review-page';

const FIRST = '2026-11-02';
const SECOND = '2026-11-09';

function week(start: string, workouts = 0): ReviewableWeek {
  return {
    week_start: start,
    has_plan: workouts > 0,
    workout_count: workouts,
    has_feedback: false,
  };
}

/** Five weeks, the plans in the second and the fourth: the latest of them is `FIRST`. */
const WEEKS: ReviewableWeek[] = [
  week('2026-10-12'),
  week('2026-10-19', 3),
  week('2026-10-26'),
  week(FIRST, 2),
  week(SECOND),
];

const FIGURES = {
  planned_count: 2,
  planned_minutes: 120,
  actual_count: 2,
  actual_minutes: 100,
  load: 360,
  rated_count: 1,
};

function workout(changes: Partial<ReviewWorkout> = {}): ReviewWorkout {
  return {
    id: 'w1',
    day: '2026-11-02',
    position: 0,
    sport: 'running',
    title: 'Easy run',
    goal: 'endurance',
    duration_minutes: 60,
    slot: null,
    notes: '',
    status: 'done',
    status_origin: 'auto',
    activity_id: 'a1',
    activity_origin: 'auto',
    ...changes,
  };
}

function activity(changes: Partial<ReviewActivity> = {}): ReviewActivity {
  return {
    id: 'a1',
    source: 'manual',
    sport: 'running',
    start_time: '2026-11-02T07:00:00Z',
    day: '2026-11-02',
    elapsed_seconds: null,
    timer_seconds: 3600,
    distance_m: 10400,
    rpe: 6,
    notes: '',
    load: 360,
    workout_id: 'w1',
    ...changes,
  };
}

function review(changes: Partial<WeekReview> = {}): WeekReview {
  return {
    week_start: FIRST,
    today: '2026-11-08',
    plan: { id: 'p1', version: 1, confirmed_at: '2026-11-01T18:00:00Z' },
    workouts: [
      workout(),
      workout({
        id: 'w2',
        day: '2026-11-04',
        sport: 'cycling',
        title: 'Ride',
        status: 'missed',
        activity_id: null,
        activity_origin: null,
      }),
    ],
    activities: [
      activity(),
      activity({
        id: 'a2',
        sport: 'strength',
        start_time: '2026-11-06T18:00:00Z',
        day: '2026-11-06',
        timer_seconds: 1800,
        distance_m: null,
        rpe: null,
        load: null,
        workout_id: null,
      }),
    ],
    comparison: {
      sports: [
        { sport: 'running', ...FIGURES, actual_count: 1, actual_minutes: 60 },
        {
          sport: 'cycling',
          ...FIGURES,
          actual_count: 0,
          actual_minutes: 0,
          load: 0,
          rated_count: 0,
        },
        {
          sport: 'strength',
          planned_count: 0,
          planned_minutes: 0,
          actual_count: 1,
          actual_minutes: 30,
          load: 0,
          rated_count: 0,
        },
      ],
      total: FIGURES,
      statuses: { done: 1, partial: 0, missed: 1, replaced: 0, open: 0 },
      done_percent: 50,
    },
    feedback: null,
    comment: null,
    ...changes,
  };
}

const ok = (shown: WeekReview = review()): GetReviewResult => ({ kind: 'ok', review: shown });
const weeksOk = (list: ReviewableWeek[] = WEEKS): ListReviewWeeksResult => ({
  kind: 'ok',
  weeks: list,
});

function createStubs() {
  return {
    api: {
      weeks: vi.fn<() => Promise<ListReviewWeeksResult>>(),
      week: vi.fn<(week: string) => Promise<GetReviewResult>>(),
      correct: vi.fn<(week: string, workoutId: string, input: unknown) => Promise<CorrectResult>>(),
      saveFeedback: vi.fn<(week: string, input: unknown) => Promise<SaveFeedbackResult>>(),
      askCoach: vi.fn<(week: string) => Promise<AskCoachResult>>(),
    },
    activities: { rate: vi.fn<(id: string, input: unknown) => Promise<RateActivityResult>>() },
    planning: { generate: vi.fn<(week: string, note?: string) => Promise<GenerateResult>>() },
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('ReviewPage', () => {
  let stubs: ReturnType<typeof createStubs>;
  let fixture: ComponentFixture<ReviewPage>;
  let page: HTMLElement;

  async function setup(
    options: { weeks?: ListReviewWeeksResult; shown?: GetReviewResult; address?: string } = {},
  ) {
    stubs = createStubs();
    stubs.api.weeks.mockResolvedValue(options.weeks ?? weeksOk());
    stubs.api.week.mockResolvedValue(options.shown ?? ok());
    create(options.address);
    await settle(fixture);
  }

  /** `address` is the `week` of the query string of the page, if it has one. */
  function create(address?: string) {
    TestBed.configureTestingModule({
      imports: [ReviewPage],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap(address === undefined ? {} : { week: address }),
            },
          },
        },
        { provide: ReviewApi, useValue: stubs.api },
        { provide: ActivitiesApi, useValue: stubs.activities },
        { provide: PlanningApi, useValue: stubs.planning },
      ],
    });
    fixture = TestBed.createComponent(ReviewPage);
    page = fixture.nativeElement as HTMLElement;
  }

  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ');
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const byId = (id: string) => page.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const inWorkout = (id: string, testid: string) =>
    page.querySelector<HTMLElement>(`[data-testid="workout-${id}"] [data-testid="${testid}"]`);
  const weekSelect = () => query<HTMLSelectElement>(page, '#review-week');
  const notice = () => page.querySelector('.notice')?.textContent?.trim();
  const save = (id: string) => query<HTMLButtonElement>(page, `[data-testid="save-${id}"]`);

  /** What the user does in the correction of a workout, before pressing Save. */
  function choose(id: string, activityValue: string, statusValue = '') {
    query<HTMLSelectElement>(page, `#activity-${id}`).value = activityValue;
    query<HTMLSelectElement>(page, `#state-${id}`).value = statusValue;
  }

  async function press(id: string) {
    save(id).click();
    await settle(fixture);
  }

  async function selectWeek(value: string) {
    const element = weekSelect();
    element.value = value;
    element.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a message while it waits', async () => {
      stubs = createStubs();
      stubs.api.weeks.mockReturnValue(deferred<ListReviewWeeksResult>().promise);
      create();
      await fixture.whenStable();

      expect(page.querySelector('[role="status"][aria-label="Loading"]')).toBeTruthy();
    });

    it('offers to try again when the weeks cannot be loaded', async () => {
      stubs = createStubs();
      stubs.api.weeks.mockRejectedValueOnce(new Error('down'));
      stubs.api.weeks.mockResolvedValue(weeksOk());
      stubs.api.week.mockResolvedValue(ok());
      create();
      await settle(fixture);

      expect(alerts()).toEqual(['Your weeks could not be loaded.']);

      query<HTMLButtonElement>(page, 'button.btn-primary').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(weekSelect()).toBeTruthy();
    });

    it.each([
      ['the weeks', { weeks: { kind: 'forbidden' } as ListReviewWeeksResult }],
      ['the week', { shown: { kind: 'forbidden' } as GetReviewResult }],
    ])('says when the session has ended (%s)', async (_name, options) => {
      await setup(options);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a[href="/login"]')).toBeTruthy();
    });
  });

  describe('the weeks', () => {
    it('lists the weeks with what each holds', async () => {
      await setup();

      const options = Array.from(weekSelect().options).map((option) => option.textContent?.trim());
      expect(options).toEqual([
        '12 Oct – 18 Oct · no plan',
        '19 Oct – 25 Oct · 3 workouts',
        '26 Oct – 1 Nov · no plan',
        '2 Nov – 8 Nov · 2 workouts',
        '9 Nov – 15 Nov · no plan',
      ]);
    });

    it('starts with the latest week that has a plan', async () => {
      await setup();

      expect(weekSelect().value).toBe(FIRST);
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(FIRST);
    });

    it('starts with the current week if no week has a plan', async () => {
      await setup({ weeks: weeksOk([week('2026-11-02'), week(SECOND)]) });

      expect(weekSelect().value).toBe(SECOND);
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(SECOND);
    });

    it('opens the week the address names', async () => {
      await setup({ address: '2026-10-19' });

      expect(weekSelect().value).toBe('2026-10-19');
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith('2026-10-19');
    });

    it('ignores a week in the address that is not in the list', async () => {
      await setup({ address: '2026-01-05' });

      expect(weekSelect().value).toBe(FIRST);
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(FIRST);
    });

    it('works without any week', async () => {
      await setup({ weeks: weeksOk([]) });

      expect(weekSelect().options.length).toBe(0);
      expect(stubs.api.week).not.toHaveBeenCalled();
      expect(alerts()).toEqual([]);
    });

    it('opens another week and drops the messages and the old week', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'activity_taken' });
      await press('w1');
      expect(alerts().length).toBe(1);
      const pending = deferred<GetReviewResult>();
      stubs.api.week.mockReturnValue(pending.promise);

      await selectWeek('2026-10-19');

      expect(stubs.api.week).toHaveBeenLastCalledWith('2026-10-19');
      expect(alerts()).toEqual([]);
      expect(byId('week')).toBeNull();
      expect(byId('opening')).toBeTruthy();
      pending.resolve(ok(review({ week_start: '2026-10-19', workouts: [], activities: [] })));
      await settle(fixture);
      expect(byId('opening')).toBeNull();
      expect(byId('week')).toBeTruthy();
    });

    it('ignores a week that is not in the list', async () => {
      await setup();
      stubs.api.week.mockClear();

      await fixture.componentInstance['selectWeek']('2020-01-06');

      expect(stubs.api.week).not.toHaveBeenCalled();
      expect(weekSelect().value).toBe(FIRST);
    });

    it('says so when a week cannot be loaded, and keeps the list', async () => {
      await setup();
      stubs.api.week.mockRejectedValue(new Error('down'));

      await selectWeek('2026-10-19');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(weekSelect()).toBeTruthy();
    });

    it('says so and fetches the weeks again when a week cannot be reviewed any more', async () => {
      await setup();
      stubs.api.week.mockResolvedValue({ kind: 'not_reviewable' });
      stubs.api.weeks.mockResolvedValue(weeksOk([week(SECOND)]));

      await selectWeek('2026-10-19');

      expect(alerts()).toEqual(['This week cannot be reviewed.']);
      expect(Array.from(weekSelect().options).map((option) => option.value)).toEqual([SECOND]);
    });
  });

  describe('a week', () => {
    it('shows how many workouts are done and the statuses', async () => {
      await setup();

      expect(byId('summary')?.textContent?.trim()).toBe('1 of 2 workouts done (50 %).');
      const badges = Array.from(page.querySelectorAll('.statuses li')).map((e) =>
        e.textContent?.trim(),
      );
      expect(badges).toEqual(['Done: 1', 'Missed: 1']);
    });

    it('shows the workouts by day with their status and what was done', async () => {
      await setup();

      expect(Array.from(page.querySelectorAll('.week > h2')).map((h) => h.textContent)).toEqual([
        'Mon 2 Nov',
        'Wed 4 Nov',
        'Not planned',
        'Planned and done',
      ]);
      expect(inWorkout('w1', 'status')?.textContent).toBe('Done');
      expect(inWorkout('w1', 'planned')?.textContent?.trim()).toBe('Planned: 1 h');
      expect(inWorkout('w1', 'matched')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
        'Done: Running · 1:00:00 · 10.40 km · RPE 6 · 360 AU',
      );
      expect(inWorkout('w2', 'status')?.textContent).toBe('Missed');
    });

    it('says when no activity was found, and when the user said there is none', async () => {
      await setup({
        shown: ok(
          review({
            workouts: [
              workout({ id: 'w2', status: 'missed', activity_id: null, activity_origin: null }),
              workout({
                id: 'w3',
                position: 1,
                status: 'missed',
                status_origin: 'user',
                activity_id: null,
                activity_origin: 'user',
              }),
            ],
          }),
        ),
      });

      expect(inWorkout('w2', 'no-activity')?.textContent?.trim()).toBe(
        'No activity found for this workout.',
      );
      expect(inWorkout('w3', 'no-activity')?.textContent?.trim()).toBe(
        'You said that no activity belongs to this workout.',
      );
      expect(inWorkout('w2', 'by-you')).toBeNull();
      expect(inWorkout('w3', 'by-you')?.textContent?.trim()).toBe('Set by you.');
    });

    it('marks what the user decided', async () => {
      await setup({
        shown: ok(review({ workouts: [workout({ status: 'partial', status_origin: 'user' })] })),
      });

      expect(inWorkout('w1', 'by-you')).toBeTruthy();
    });

    it('lists what was not planned', async () => {
      await setup();

      const items = Array.from(page.querySelectorAll('[data-testid="unplanned"] li')).map((li) =>
        li.textContent?.replace(/\s+/g, ' ').trim(),
      );
      // The rating form of the session follows the text; only what comes first is of interest.
      expect(items).toEqual([expect.stringMatching(/^Fri 6 Nov · Strength · 30:00 · Not rated/)]);
    });

    it('has no such list when everything was planned', async () => {
      await setup({ shown: ok(review({ activities: [activity()] })) });

      expect(byId('unplanned')).toBeNull();
      expect(text()).not.toContain('Not planned');
    });

    it('compares planned and done per sport and together', async () => {
      await setup();

      const row = (id: string) =>
        Array.from(page.querySelectorAll(`[data-testid="${id}"] > *`)).map((cell) =>
          cell.textContent?.trim(),
        );
      expect(row('figures-running')).toEqual(['Running', '2 · 2 h', '1 · 1 h', '360 AU']);
      expect(row('figures-cycling')).toEqual(['Cycling', '2 · 2 h', '0 · 0 min', '–']);
      expect(row('figures-strength')).toEqual(['Strength', '0 · 0 min', '1 · 30 min', '–']);
      expect(row('figures-total')).toEqual([
        'Together',
        '2 · 2 h',
        '2 · 1 h 40 min',
        '360 AU (1 of 2 rated)',
      ]);
      expect(text()).toContain('It is not the TSS of a platform.');
    });

    it('shows a week without a plan with what was done and a way to the plan', async () => {
      await setup({
        shown: ok(
          review({
            plan: null,
            workouts: [],
            activities: [activity({ workout_id: null })],
            comparison: {
              sports: [{ sport: 'running', ...FIGURES, planned_count: 0, planned_minutes: 0 }],
              total: FIGURES,
              statuses: { done: 0, partial: 0, missed: 0, replaced: 0, open: 0 },
              done_percent: null,
            },
          }),
        ),
      });

      expect(byId('no-plan')?.textContent).toContain('There is no confirmed plan for this week.');
      expect(page.querySelector('[data-testid="no-plan"] a[href="/planning"]')).toBeTruthy();
      expect(byId('summary')).toBeNull();
      expect(byId('unplanned')).toBeTruthy();
    });

    it('says that no workout is over yet', async () => {
      await setup({
        shown: ok(
          review({
            workouts: [workout({ status: 'open', activity_id: null, activity_origin: null })],
            activities: [],
            comparison: {
              ...review().comparison,
              statuses: { done: 0, partial: 0, missed: 0, replaced: 0, open: 1 },
              done_percent: null,
            },
          }),
        ),
      });

      expect(byId('summary')?.textContent?.trim()).toBe('None of the workouts is over yet.');
      expect(inWorkout('w1', 'status')?.textContent).toBe('Open');
    });

    it('shows titles and notes as text and never as markup', async () => {
      await setup({
        shown: ok(
          review({
            workouts: [workout({ title: '<b>Hills</b><img src=x onerror=alert(1)>' })],
            activities: [activity({ notes: '<script>alert(1)</script> felt good' })],
          }),
        ),
      });

      expect(text()).toContain('<b>Hills</b><img src=x onerror=alert(1)>');
      expect(byId('matched-notes')?.textContent).toBe('<script>alert(1)</script> felt good');
      expect(page.querySelector('.workout b, .workout img, .week script')).toBeNull();
    });
  });

  describe('correcting a workout', () => {
    it('offers the activities of the week, no activity and the statuses', async () => {
      await setup();

      const activities = Array.from(query<HTMLSelectElement>(page, '#activity-w1').options);
      expect(activities.map((option) => [option.value, option.textContent?.trim()])).toEqual([
        ['', 'Match automatically'],
        ['none', 'No activity'],
        ['a1', 'Mon 2 Nov · Running · 1:00:00 · 10.40 km'],
        ['a2', 'Fri 6 Nov · Strength · 30:00'],
      ]);
      const statuses = Array.from(query<HTMLSelectElement>(page, '#state-w1').options);
      expect(statuses.map((option) => option.value)).toEqual([
        '',
        'done',
        'partial',
        'missed',
        'replaced',
      ]);
    });

    it('shows what the user has decided and leaves the rest automatic', async () => {
      await setup({
        shown: ok(
          review({
            workouts: [
              workout({
                activity_origin: 'user',
                status: 'partial',
                status_origin: 'user',
              }),
              workout({
                id: 'w2',
                position: 1,
                status: 'missed',
                activity_id: null,
                activity_origin: 'user',
              }),
              workout({ id: 'w3', position: 2, activity_id: 'a2' }),
            ],
          }),
        ),
      });

      expect(query<HTMLSelectElement>(page, '#activity-w1').value).toBe('a1');
      expect(query<HTMLSelectElement>(page, '#state-w1').value).toBe('partial');
      expect(query<HTMLSelectElement>(page, '#activity-w2').value).toBe('none');
      expect(query<HTMLSelectElement>(page, '#state-w2').value).toBe('');
      expect(query<HTMLSelectElement>(page, '#activity-w3').value).toBe('');
    });

    it('sends the choices as a decision and shows the week that comes back', async () => {
      await setup();
      const changed = review({ workouts: [workout({ title: 'Easy run (changed)' })] });
      stubs.api.correct.mockResolvedValue({ kind: 'ok', review: changed });
      choose('w2', 'a2', 'replaced');

      await press('w2');

      expect(stubs.api.correct).toHaveBeenCalledExactlyOnceWith(FIRST, 'w2', {
        activity: 'a2',
        no_activity: false,
        status: 'replaced',
      });
      expect(page.querySelector('h3')?.textContent).toBe('Easy run (changed)');
      expect(notice()).toBe('Saved.');
      expect(weekSelect().value).toBe(FIRST);
    });

    it.each([
      ['none', '', { activity: null, no_activity: true, status: '' }],
      ['', '', { activity: null, no_activity: false, status: '' }],
      ['', 'missed', { activity: null, no_activity: false, status: 'missed' }],
    ])('sends %j with status %j', async (value, status, expected) => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'ok', review: review() });
      choose('w1', value, status);

      await press('w1');

      expect(stubs.api.correct).toHaveBeenCalledExactlyOnceWith(FIRST, 'w1', expected);
    });

    it('shows what the server refused, by field', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({
        kind: 'invalid',
        errors: {
          status: ['This status needs an activity. Link one first.'],
          activity: ['Choose an activity of this week.'],
        },
        message: null,
      });
      choose('w2', '', 'done');

      await press('w2');

      expect(alerts()).toEqual([
        'Choose an activity of this week.',
        'This status needs an activity. Link one first.',
      ]);
      expect(notice()).toBeUndefined();
    });

    it('shows a general refusal', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({
        kind: 'invalid',
        errors: {},
        message: 'Your entries could not be saved. Please check them.',
      });

      await press('w1');

      expect(alerts()).toEqual(['Your entries could not be saved. Please check them.']);
    });

    it('keeps what the user chose after a refusal', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'activity_taken' });
      choose('w2', 'a1', 'partial');

      await press('w2');

      expect(alerts()).toEqual([
        'That activity is already assigned to another workout. Free it there first.',
      ]);
      expect(query<HTMLSelectElement>(page, '#activity-w2').value).toBe('a1');
      expect(query<HTMLSelectElement>(page, '#state-w2').value).toBe('partial');
    });

    it('fetches the week again when the workout is not in the plan any more', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'workout_not_found' });
      stubs.api.week.mockClear();

      await press('w1');

      expect(alerts()).toEqual(['That workout is not in the plan of this week any more.']);
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(FIRST);
    });

    it('fetches the weeks again when the week cannot be reviewed any more', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'not_reviewable' });
      stubs.api.weeks.mockClear();

      await press('w1');

      expect(alerts()).toEqual(['This week cannot be reviewed.']);
      expect(stubs.api.weeks).toHaveBeenCalledTimes(1);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'forbidden' });

      await press('w1');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when saving fails', async () => {
      await setup();
      stubs.api.correct.mockRejectedValue(new Error('down'));

      await press('w1');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(save('w1').disabled).toBe(false);
    });

    it('allows one thing at a time', async () => {
      await setup();
      const pending = deferred<CorrectResult>();
      stubs.api.correct.mockReturnValue(pending.promise);

      save('w1').click();
      await fixture.whenStable();

      expect(save('w1').disabled).toBe(true);
      expect(save('w2').disabled).toBe(true);
      expect(weekSelect().disabled).toBe(true);
      expect(query<HTMLSelectElement>(page, '#activity-w1').disabled).toBe(true);

      await fixture.componentInstance['correct'](workout(), '', '');
      expect(stubs.api.correct).toHaveBeenCalledTimes(1);

      pending.resolve({ kind: 'ok', review: review() });
      await settle(fixture);
      expect(save('w1').disabled).toBe(false);
    });
  });

  describe('rating a session', () => {
    const rateButton = (id: string) =>
      query<HTMLButtonElement>(page, `[data-testid="rating-save-${id}"]`);

    function rateWith(id: string, rpe: string, notes: string) {
      const select = query<HTMLSelectElement>(page, `#rpe-${id}`);
      select.value = rpe;
      select.dispatchEvent(new Event('change'));
      const note = query<HTMLTextAreaElement>(page, `#notes-${id}`);
      note.value = notes;
      note.dispatchEvent(new Event('input'));
      rateButton(id).click();
    }

    it('offers it for the session of a workout and for one that was not planned', async () => {
      await setup();

      expect(byId('rate-a1')?.textContent?.trim()).toBe('Change the rating');
      expect(byId('rate-a2')?.textContent?.trim()).toBe('Rate this session');
      expect(page.querySelectorAll('app-session-rating').length).toBe(2);
    });

    it('rates the session, fetches the week again and shows the load that follows', async () => {
      await setup();
      stubs.activities.rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
      stubs.api.week.mockResolvedValue(
        ok(
          review({
            activities: [activity({ rpe: 7, load: 420, notes: 'Hilly' }), review().activities[1]],
          }),
        ),
      );
      stubs.api.week.mockClear();

      rateWith('a1', '7', 'Hilly');
      await settle(fixture);

      expect(stubs.activities.rate).toHaveBeenCalledExactlyOnceWith('a1', {
        rpe: 7,
        notes: 'Hilly',
      });
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(FIRST);
      expect(inWorkout('w1', 'matched')?.textContent).toContain('RPE 7 · 420 AU');
      expect(inWorkout('w1', 'matched-notes')?.textContent).toBe('Hilly');
      expect(notice()).toBe('The rating was saved.');
      expect(weekSelect().value).toBe(FIRST);
    });

    it('rates a session that was not planned', async () => {
      await setup();
      stubs.activities.rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
      stubs.api.week.mockResolvedValue(
        ok(
          review({
            activities: [activity(), { ...review().activities[1], rpe: 5, load: 150 }],
          }),
        ),
      );

      rateWith('a2', '5', '');
      await settle(fixture);

      expect(stubs.activities.rate).toHaveBeenCalledExactlyOnceWith('a2', { rpe: 5, notes: '' });
      expect(byId('unplanned-a2')?.textContent).toContain('RPE 5 · 150 AU');
    });

    it('does not say that it worked when the week cannot be fetched again', async () => {
      await setup();
      stubs.activities.rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
      stubs.api.week.mockRejectedValue(new Error('down'));

      rateWith('a1', '7', '');
      await settle(fixture);

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(notice()).toBeUndefined();
    });

    it('says so and shows the week as it is when the session is gone', async () => {
      await setup();
      stubs.activities.rate.mockResolvedValue({ kind: 'not_found' });
      stubs.api.week.mockClear();

      rateWith('a1', '7', '');
      await settle(fixture);

      expect(alerts()).toEqual(['That session does not exist any more.']);
      expect(stubs.api.week).toHaveBeenCalledExactlyOnceWith(FIRST);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.activities.rate.mockResolvedValue({ kind: 'forbidden' });

      rateWith('a1', '7', '');
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('is switched off while the page is busy', async () => {
      await setup();
      const pending = deferred<CorrectResult>();
      stubs.api.correct.mockReturnValue(pending.promise);

      save('w1').click();
      await fixture.whenStable();

      expect(rateButton('a1').disabled).toBe(true);
      expect(rateButton('a2').disabled).toBe(true);
      pending.resolve({ kind: 'ok', review: review() });
      await settle(fixture);
      expect(rateButton('a1').disabled).toBe(false);
    });
  });

  describe('feedback on the week', () => {
    const feedbackButton = () => query<HTMLButtonElement>(page, '[data-testid="feedback-save"]');

    function giveFeedback(fatigue: string, notes: string) {
      const select = query<HTMLSelectElement>(page, '#feedback-fatigue');
      select.value = fatigue;
      select.dispatchEvent(new Event('change'));
      const note = query<HTMLTextAreaElement>(page, '#feedback-notes');
      note.value = notes;
      note.dispatchEvent(new Event('input'));
      feedbackButton().click();
    }

    it('shows the form for the week', async () => {
      await setup();

      expect(page.querySelector('app-week-feedback-form')).toBeTruthy();
    });

    it('shows the form for a week without a plan too', async () => {
      await setup({ shown: ok(review({ plan: null, workouts: [], activities: [] })) });

      expect(page.querySelector('app-week-feedback-form')).toBeTruthy();
    });

    it('shows the feedback that is stored', async () => {
      await setup({
        shown: ok(
          review({
            feedback: {
              fatigue: 4,
              motivation: null,
              pain: 1,
              verdict: 'good',
              notes: 'Heavy legs',
              updated_at: '2026-11-08T08:00:00Z',
            },
          }),
        ),
      });

      expect(query<HTMLSelectElement>(page, '#feedback-fatigue').value).toBe('4');
      expect(query<HTMLSelectElement>(page, '#feedback-verdict').value).toBe('good');
      expect(query<HTMLTextAreaElement>(page, '#feedback-notes').value).toBe('Heavy legs');
    });

    it('saves it for the selected week and shows the week that comes back', async () => {
      await setup();
      const answer = review({
        feedback: {
          fatigue: 3,
          motivation: null,
          pain: null,
          verdict: null,
          notes: 'Fine',
          updated_at: '2026-11-08T08:00:00Z',
        },
      });
      stubs.api.saveFeedback.mockResolvedValue({ kind: 'ok', review: answer });

      giveFeedback('3', 'Fine');
      await settle(fixture);

      expect(stubs.api.saveFeedback).toHaveBeenCalledExactlyOnceWith(FIRST, {
        fatigue: 3,
        motivation: null,
        pain: null,
        verdict: null,
        notes: 'Fine',
      });
      expect(notice()).toBe('Your feedback was saved.');
      expect(query<HTMLSelectElement>(page, '#feedback-fatigue').value).toBe('3');
      expect(weekSelect().value).toBe(FIRST);
    });

    it('drops an earlier error when it was saved', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'activity_taken' });
      await press('w1');
      expect(alerts().length).toBe(1);
      stubs.api.saveFeedback.mockResolvedValue({ kind: 'ok', review: review() });

      giveFeedback('2', '');
      await settle(fixture);

      expect(alerts()).toEqual([]);
    });

    it('says so and fetches the weeks again when the week cannot be reviewed any more', async () => {
      await setup();
      stubs.api.saveFeedback.mockResolvedValue({ kind: 'not_reviewable' });
      stubs.api.weeks.mockClear();

      giveFeedback('2', '');
      await settle(fixture);

      expect(alerts()).toEqual(['This week cannot be reviewed.']);
      expect(stubs.api.weeks).toHaveBeenCalledTimes(1);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.api.saveFeedback.mockResolvedValue({ kind: 'forbidden' });

      giveFeedback('2', '');
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('is switched off while the page is busy', async () => {
      await setup();
      const pending = deferred<CorrectResult>();
      stubs.api.correct.mockReturnValue(pending.promise);

      save('w1').click();
      await fixture.whenStable();

      expect(feedbackButton().disabled).toBe(true);
      pending.resolve({ kind: 'ok', review: review() });
      await settle(fixture);
      expect(feedbackButton().disabled).toBe(false);
    });
  });

  describe('closing the week', () => {
    const closeButton = () => query<HTMLButtonElement>(page, '[data-testid="feedback-close"]');
    const NEXT = '2026-11-09';
    let navigate: ReturnType<typeof vi.spyOn>;

    function close(note = '', verdict = 'good') {
      const judge = query<HTMLSelectElement>(page, '#feedback-verdict');
      judge.value = verdict;
      judge.dispatchEvent(new Event('change'));
      const field = query<HTMLTextAreaElement>(page, '#next-week-note');
      field.value = note;
      field.dispatchEvent(new Event('input'));
      closeButton().click();
    }

    async function ready(answer: GenerateResult) {
      await setup();
      navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
      stubs.api.saveFeedback.mockResolvedValue({ kind: 'ok', review: review() });
      stubs.planning.generate.mockResolvedValue(answer);
    }

    const DRAFTED: GenerateResult = { kind: 'ok', plan: { id: 'p1' } as never };

    it('saves the feedback, drafts the week after it with the note and opens it', async () => {
      await ready(DRAFTED);

      close('No time on Tuesday.', 'strong');
      await settle(fixture);

      expect(stubs.api.saveFeedback).toHaveBeenCalledExactlyOnceWith(
        FIRST,
        expect.objectContaining({ verdict: 'strong' }),
      );
      expect(stubs.planning.generate).toHaveBeenCalledExactlyOnceWith(NEXT, 'No time on Tuesday.');
      expect(navigate).toHaveBeenCalledExactlyOnceWith(['/planning'], {
        queryParams: { week: NEXT },
      });
    });

    it('asks nothing of the coach when the feedback could not be saved', async () => {
      await ready(DRAFTED);
      stubs.api.saveFeedback.mockResolvedValue({
        kind: 'invalid',
        errors: { verdict: ['Choose one of the verdicts.'] },
        message: null,
      });

      close('A note');
      await settle(fixture);

      expect(stubs.planning.generate).not.toHaveBeenCalled();
      expect(navigate).not.toHaveBeenCalled();
    });

    it('says that the coach is drafting, and allows nothing else meanwhile', async () => {
      await ready(DRAFTED);
      const pending = deferred<GenerateResult>();
      stubs.planning.generate.mockReturnValue(pending.promise);

      close('A note');
      await settle(fixture);

      expect(byId('drafting')?.textContent).toContain('drafting the next week');
      expect(closeButton().disabled).toBe(true);
      expect(weekSelect().disabled).toBe(true);
      pending.resolve(DRAFTED);
      await settle(fixture);
      expect(byId('drafting')).toBeNull();
    });

    it('keeps the feedback and the week when the coach could not draft, and says why', async () => {
      await ready({ kind: 'not_usable', problems: [] });

      close('A note');
      await settle(fixture);

      expect(notice()).toBe('Your feedback was saved.');
      expect(alerts()).toEqual([
        'The coach did not give a plan that could be used. Please try again.',
      ]);
      expect(navigate).not.toHaveBeenCalled();
      expect(query<HTMLTextAreaElement>(page, '#next-week-note').value).toBe('A note');
      expect(closeButton().disabled).toBe(false);
    });

    it.each([
      [
        { kind: 'invalid', message: 'Use at most 300 characters.' } as GenerateResult,
        'Use at most 300 characters.',
      ],
      [
        { kind: 'not_plannable' } as GenerateResult,
        'The week after this one cannot be planned (only the current week and the next four can).',
      ],
      [
        { kind: 'not_configured' } as GenerateResult,
        'No AI provider is set up, so the next week was not drafted.',
      ],
      [
        { kind: 'no_time' } as GenerateResult,
        'You have no training time for the next week, so it was not drafted.',
      ],
      [
        { kind: 'rate_limited', retry_after: null } as GenerateResult,
        'Too many plans were requested. Please wait a minute and try again.',
      ],
      [
        {
          kind: 'provider_problem',
          problem: 'unavailable',
          message: 'Your AI provider could not be reached.',
          retry_after: 20,
        } as GenerateResult,
        'Your AI provider could not be reached. Try again in 20 seconds.',
      ],
      [
        {
          kind: 'provider_problem',
          problem: 'invalid_key',
          message: 'Your AI provider did not accept the key.',
          retry_after: null,
        } as GenerateResult,
        'Your AI provider did not accept the key.',
      ],
    ])('says what went wrong when drafting did not work: %j', async (answer, expected) => {
      await ready(answer);

      close('A note');
      await settle(fixture);

      expect(alerts()).toEqual([expected]);
      expect(navigate).not.toHaveBeenCalled();
    });

    it('says so when drafting fails without an answer', async () => {
      await ready(DRAFTED);
      stubs.planning.generate.mockRejectedValue(new Error('down'));

      close('A note');
      await settle(fixture);

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(notice()).toBe('Your feedback was saved.');
    });

    it('says when the session has ended while drafting', async () => {
      await ready({ kind: 'forbidden' });

      close('A note');
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('drafts the week after the one that is shown, whichever it is', async () => {
      await setup({ shown: ok(review({ week_start: '2026-10-19' })) });
      navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
      stubs.api.saveFeedback.mockResolvedValue({
        kind: 'ok',
        review: review({ week_start: '2026-10-19' }),
      });
      stubs.planning.generate.mockResolvedValue(DRAFTED);

      close('');
      await settle(fixture);

      expect(stubs.planning.generate).toHaveBeenCalledExactlyOnceWith('2026-10-26', '');
    });

    it('can be done again after a failure', async () => {
      await ready({ kind: 'not_usable', problems: [] });
      close('A note');
      await settle(fixture);
      stubs.planning.generate.mockResolvedValue(DRAFTED);

      closeButton().click();
      await settle(fixture);

      expect(stubs.planning.generate).toHaveBeenCalledTimes(2);
      expect(alerts()).toEqual([]);
      expect(navigate).toHaveBeenCalledTimes(1);
    });
  });

  describe('the comment of the coach', () => {
    const askButton = () => query<HTMLButtonElement>(page, '[data-testid="ask"]');
    const COMMENT = {
      comment: 'One of two done.',
      next_week: 'hold' as const,
      created_at: '2026-11-15T08:00:00Z',
    };

    it('shows the section for the week, also for a week without a plan', async () => {
      await setup();
      expect(page.querySelector('app-coach-comment')).toBeTruthy();
      expect(byId('coach-none')).toBeTruthy();
    });

    it('shows the comment that is stored', async () => {
      await setup({ shown: ok(review({ comment: COMMENT })) });

      expect(byId('coach-text')?.textContent).toBe('One of two done.');
      expect(byId('coach-recommendation')?.textContent).toContain('keep the volume about the same');
    });

    it('tells the coach is not over when workouts are open', async () => {
      await setup({
        shown: ok(
          review({
            comparison: {
              ...review().comparison,
              statuses: { done: 1, partial: 0, missed: 0, replaced: 0, open: 2 },
            },
          }),
        ),
      });

      expect(byId('coach-open')?.textContent).toContain('2 workouts of this week are');
    });

    it('asks for the selected week and shows the week that comes back', async () => {
      await setup();
      stubs.api.askCoach.mockResolvedValue({
        kind: 'ok',
        review: review({ comment: COMMENT }),
      });

      askButton().click();
      await settle(fixture);

      expect(stubs.api.askCoach).toHaveBeenCalledExactlyOnceWith(FIRST);
      expect(byId('coach-text')?.textContent).toBe('One of two done.');
      expect(notice()).toBe('Your coach commented on the week.');
      expect(weekSelect().value).toBe(FIRST);
    });

    it('drops an earlier error when the coach commented', async () => {
      await setup();
      stubs.api.correct.mockResolvedValue({ kind: 'activity_taken' });
      await press('w1');
      expect(alerts().length).toBe(1);
      stubs.api.askCoach.mockResolvedValue({ kind: 'ok', review: review() });

      askButton().click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
    });

    it('switches everything else off while the coach is asked', async () => {
      await setup();
      const pending = deferred<AskCoachResult>();
      stubs.api.askCoach.mockReturnValue(pending.promise);

      askButton().click();
      await fixture.whenStable();

      expect(weekSelect().disabled).toBe(true);
      expect(save('w1').disabled).toBe(true);
      expect(query<HTMLButtonElement>(page, '[data-testid="feedback-save"]').disabled).toBe(true);
      expect(query<HTMLButtonElement>(page, '[data-testid="rating-save-a1"]').disabled).toBe(true);
      expect(byId('coach-waiting')).toBeTruthy();

      pending.resolve({ kind: 'ok', review: review() });
      await settle(fixture);

      expect(weekSelect().disabled).toBe(false);
      expect(save('w1').disabled).toBe(false);
    });

    it('does not let another action start while the coach is asked', async () => {
      await setup();
      const pending = deferred<AskCoachResult>();
      stubs.api.askCoach.mockReturnValue(pending.promise);
      askButton().click();
      await fixture.whenStable();

      await fixture.componentInstance['selectWeek']('2026-10-19');
      await fixture.componentInstance['correct'](workout(), '', '');

      expect(stubs.api.week).toHaveBeenCalledTimes(1);
      expect(stubs.api.correct).not.toHaveBeenCalled();
      pending.resolve({ kind: 'forbidden' });
      await settle(fixture);
    });

    it('says so and fetches the weeks again when the week cannot be reviewed any more', async () => {
      await setup();
      stubs.api.askCoach.mockResolvedValue({ kind: 'not_reviewable' });
      stubs.api.weeks.mockClear();

      askButton().click();
      await settle(fixture);

      expect(alerts()).toEqual(['This week cannot be reviewed.']);
      expect(stubs.api.weeks).toHaveBeenCalledTimes(1);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.api.askCoach.mockResolvedValue({ kind: 'forbidden' });

      askButton().click();
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows what went wrong next to the button and keeps the week', async () => {
      await setup();
      stubs.api.askCoach.mockResolvedValue({ kind: 'not_configured' });

      askButton().click();
      await settle(fixture);

      expect(byId('coach-message')?.textContent).toContain('No AI provider is set up.');
      expect(byId('week')).toBeTruthy();
    });
  });
});
