import { Comparison, ReviewActivity, ReviewWorkout } from '../../core/review/review-models';
import {
  AUTOMATIC,
  NONE,
  activityChoiceText,
  activitySize,
  choiceOf,
  correctionOf,
  countAndMinutes,
  doneShareText,
  loadText,
  ratingText,
  recommendationText,
  statusChoiceOf,
  weekOptionText,
} from './review-format';

const FIGURES = {
  planned_count: 2,
  planned_minutes: 120,
  planned_load: 110,
  actual_count: 2,
  actual_minutes: 100,
  load: 60,
  loaded_count: 2,
  rated_count: 2,
};

function activity(changes: Partial<ReviewActivity> = {}): ReviewActivity {
  return {
    id: 'a1',
    source: 'manual',
    sport: 'running',
    start_time: '2026-11-09T07:00:00Z',
    day: '2026-11-09',
    elapsed_seconds: null,
    timer_seconds: 3600,
    distance_m: 10400,
    rpe: 6,
    notes: '',
    load: 60,
    load_source: 'rpe',
    workout_id: null,
    ...changes,
  };
}

function workout(changes: Partial<ReviewWorkout> = {}): ReviewWorkout {
  return {
    id: 'w1',
    day: '2026-11-09',
    position: 0,
    sport: 'running',
    title: 'Easy run',
    goal: 'endurance',
    duration_minutes: 60,
    estimated_load: 55,
    slot: null,
    notes: '',
    status: 'done',
    status_origin: 'auto',
    activity_id: 'a1',
    activity_origin: 'auto',
    ...changes,
  };
}

function comparison(changes: Partial<Comparison> = {}): Comparison {
  return {
    sports: [],
    total: FIGURES,
    statuses: { done: 1, partial: 0, missed: 1, replaced: 0, open: 1 },
    done_percent: 50,
    ...changes,
  };
}

describe('review-format', () => {
  describe('weekOptionText', () => {
    it.each([
      [0, '9 Nov – 15 Nov · no plan'],
      [1, '9 Nov – 15 Nov · 1 workout'],
      [4, '9 Nov – 15 Nov · 4 workouts'],
    ])('says what the week holds (%i workouts)', (count, expected) => {
      const week = {
        week_start: '2026-11-09',
        has_plan: count > 0,
        workout_count: count,
        has_feedback: false,
      };

      expect(weekOptionText(week)).toBe(expected);
    });
  });

  describe('activities', () => {
    it('shows the duration and the distance', () => {
      expect(activitySize(activity())).toBe('1:00:00 · 10.40 km');
    });

    it('lets the elapsed time stand in for the timer time', () => {
      expect(activitySize(activity({ timer_seconds: null, elapsed_seconds: 1800 }))).toBe(
        '30:00 · 10.40 km',
      );
    });

    it('leaves out what is not there, and says so when nothing is', () => {
      expect(activitySize(activity({ distance_m: null }))).toBe('1:00:00');
      expect(activitySize(activity({ timer_seconds: null }))).toBe('10.40 km');
      expect(activitySize(activity({ timer_seconds: null, distance_m: null }))).toBe('–');
    });

    it('names the day, the sport and the size in a choice', () => {
      expect(activityChoiceText(activity({ distance_m: null }))).toBe(
        'Mon 9 Nov · Running · 1:00:00',
      );
      expect(activityChoiceText(activity({ sport: 'other', distance_m: null }))).toContain('Other');
    });

    it.each<[Partial<ReviewActivity>, string]>([
      [{}, 'RPE 6 · 60 pts (RPE estimate)'],
      [{ load: null }, 'RPE 6'],
      [{ rpe: null, load: null }, 'Not rated'],
      [{ rpe: null, load: 80, load_source: 'intervals' }, 'Not rated · 80 pts (Intervals.icu)'],
      [{ rpe: 6, load: 80, load_source: 'intervals' }, 'RPE 6 · 80 pts (Intervals.icu)'],
      [{ rpe: null, load: 0, load_source: 'intervals' }, 'Not rated · 0 pts (Intervals.icu)'],
    ])('says how it was rated (%j)', (changes, expected) => {
      expect(ratingText(activity(changes))).toBe(expected);
    });
  });

  describe('figures', () => {
    it('shows known load and its coverage independently of ratings', () => {
      expect(loadText(FIGURES)).toBe('60 pts');
      expect(loadText({ ...FIGURES, loaded_count: 1 })).toBe('60 pts (1 of 2 with load)');
      expect(loadText({ ...FIGURES, rated_count: 0 })).toBe('60 pts');
      expect(loadText({ ...FIGURES, loaded_count: 0, load: 0 })).toBe('–');
      expect(loadText({ ...FIGURES, actual_count: 0, loaded_count: 0, load: 0 })).toBe('–');
      expect(loadText({ ...FIGURES, rated_count: 0, load: 0 })).toBe('0 pts');
    });

    it('writes a count with its minutes', () => {
      expect(countAndMinutes(2, 90)).toBe('2 · 1 h 30 min');
      expect(countAndMinutes(0, 0)).toBe('0 · 0 min');
    });

    it('says how many of the finished workouts are done', () => {
      expect(doneShareText(comparison())).toBe('1 of 2 workouts done (50 %).');
      expect(
        doneShareText(
          comparison({
            statuses: { done: 1, partial: 0, missed: 0, replaced: 0, open: 3 },
            done_percent: 100,
          }),
        ),
      ).toBe('1 of 1 workout done (100 %).');
    });

    it('says when none is over yet', () => {
      expect(
        doneShareText(
          comparison({
            statuses: { done: 0, partial: 0, missed: 0, replaced: 0, open: 2 },
            done_percent: null,
          }),
        ),
      ).toBe('None of the workouts is over yet.');
    });
  });

  describe('what the user decided', () => {
    it('shows no choice for what the server worked out', () => {
      expect(choiceOf(workout())).toBe(AUTOMATIC);
      expect(statusChoiceOf(workout())).toBe('');
    });

    it('shows the activity, or none, the user chose', () => {
      expect(choiceOf(workout({ activity_origin: 'user', activity_id: 'a9' }))).toBe('a9');
      expect(choiceOf(workout({ activity_origin: 'user', activity_id: null }))).toBe(NONE);
    });

    it('shows the status the user set, never open', () => {
      expect(statusChoiceOf(workout({ status: 'partial', status_origin: 'user' }))).toBe('partial');
      expect(statusChoiceOf(workout({ status: 'open', status_origin: 'user' }))).toBe('');
    });

    it.each([
      [AUTOMATIC, '', { activity: null, no_activity: false, status: '' }],
      [NONE, '', { activity: null, no_activity: true, status: '' }],
      ['a1', 'partial', { activity: 'a1', no_activity: false, status: 'partial' }],
      ['a1', 'nonsense', { activity: 'a1', no_activity: false, status: '' }],
      [AUTOMATIC, 'missed', { activity: null, no_activity: false, status: 'missed' }],
    ])('turns the choices %j and %j into a decision', (choice, status, expected) => {
      expect(correctionOf(choice, status)).toEqual(expected);
    });
  });

  describe('recommendationText', () => {
    it('puts the three recommendations in words', () => {
      expect(recommendationText('increase')).toBe('increase the volume a little');
      expect(recommendationText('hold')).toBe('keep the volume about the same');
      expect(recommendationText('reduce')).toBe('reduce the volume');
    });
  });
});
