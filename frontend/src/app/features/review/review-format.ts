import { Sport } from '../../core/activities/activities-models';
import {
  ChoosableStatus,
  Comparison,
  CorrectionInput,
  Figures,
  Recommendation,
  ReviewActivity,
  ReviewWorkout,
  ReviewableWeek,
  WeekVerdict,
  WorkoutStatus,
} from '../../core/review/review-models';
import { MISSING, formatDistance, formatDuration, formatLoad } from '../activities/activity-format';
import { dayLabel, minutesText, weekRange } from '../planning/plan-format';

export const STATUS_LABELS: Record<WorkoutStatus, string> = {
  done: 'Done',
  partial: 'Partial',
  missed: 'Missed',
  replaced: 'Replaced',
  open: 'Open',
};

/** The colours of the badge of a status: what was done is accent, what was missed is a warning. */
export const STATUS_STYLES: Record<WorkoutStatus, string> = {
  done: 'border-accent text-accent',
  partial: '',
  missed: 'border-danger text-danger',
  replaced: '',
  open: 'text-muted',
};

export const SPORT_LABELS: Record<Sport, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength',
  other: 'Other',
};

/** What the user may set by hand; the empty value leaves it to the activity. */
export const STATUS_CHOICES: { value: ChoosableStatus | ''; label: string }[] = [
  { value: '', label: 'Worked out from the activity' },
  { value: 'done', label: STATUS_LABELS.done },
  { value: 'partial', label: STATUS_LABELS.partial },
  { value: 'missed', label: STATUS_LABELS.missed },
  { value: 'replaced', label: STATUS_LABELS.replaced },
];

/** The values of the activity choice that are no activity. */
export const AUTOMATIC = '';
export const NONE = 'none';

/** "9 Nov – 15 Nov · 4 workouts" or "… · no plan": one week in the list. */
export function weekOptionText(week: ReviewableWeek): string {
  const plan =
    week.workout_count === 0
      ? 'no plan'
      : `${week.workout_count} ${week.workout_count === 1 ? 'workout' : 'workouts'}`;
  return `${weekRange(week.week_start)} · ${plan}`;
}

/** "1:00:00 · 10.40 km": what an activity shows of its size; a missing value is left out. */
export function activitySize(activity: ReviewActivity): string {
  const seconds = activity.timer_seconds ?? activity.elapsed_seconds;
  const parts = [seconds === null ? null : formatDuration(seconds)];
  parts.push(activity.distance_m === null ? null : formatDistance(activity.distance_m));
  return parts.filter((part): part is string => part !== null).join(' · ') || MISSING;
}

/** "Mon 9 Nov · Running · 1:00:00": an activity in a list of choices. */
export function activityChoiceText(activity: ReviewActivity): string {
  return `${dayLabel(activity.day)} · ${SPORT_LABELS[activity.sport]} · ${activitySize(activity)}`;
}

/** The rating and any known load, including Intervals load without an RPE rating. */
export function ratingText(activity: ReviewActivity): string {
  const rating = activity.rpe === null ? 'Not rated' : `RPE ${activity.rpe}`;
  return activity.load === null
    ? rating
    : `${rating} · ${formatLoad(activity.load, activity.load_source)}`;
}

/** Known done load, with coverage when some sessions have no load. */
export function loadText(figures: Figures): string {
  if (figures.loaded_count === 0) {
    return MISSING;
  }
  const partly =
    figures.loaded_count < figures.actual_count
      ? ` (${figures.loaded_count} of ${figures.actual_count} with load)`
      : '';
  return `${figures.load} pts${partly}`;
}

/** "1 of 2 · 1 h" or "0 · 0 min": a count with its minutes. */
export function countAndMinutes(count: number, minutes: number): string {
  return `${count} · ${minutesText(minutes)}`;
}

/** What the share of finished workouts says, in words. */
export function doneShareText(comparison: Comparison): string {
  const { done_percent: share, statuses } = comparison;
  if (share === null) {
    return 'None of the workouts is over yet.';
  }
  const judged = Object.values(statuses).reduce((sum, n) => sum + n, 0) - statuses.open;
  return `${statuses.done} of ${judged} ${judged === 1 ? 'workout' : 'workouts'} done (${share} %).`;
}

/** The value of the activity choice that shows what the user has decided: empty if nothing. */
export function choiceOf(workout: ReviewWorkout): string {
  if (workout.activity_origin !== 'user') {
    return AUTOMATIC;
  }
  return workout.activity_id ?? NONE;
}

/** The value of the status choice that shows what the user has decided: empty if nothing. */
export function statusChoiceOf(workout: ReviewWorkout): ChoosableStatus | '' {
  return workout.status_origin === 'user' && workout.status !== 'open' ? workout.status : '';
}

/** What the two choices of a workout mean as a decision for the server. */
export function correctionOf(choice: string, status: string): CorrectionInput {
  const known = STATUS_CHOICES.find((candidate) => candidate.value === status);
  return {
    activity: choice === AUTOMATIC || choice === NONE ? null : choice,
    no_activity: choice === NONE,
    status: known?.value ?? '',
  };
}

function scaleChoices(words: string[]): { value: number; label: string }[] {
  return words.map((label, index) => ({ value: index + 1, label: `${index + 1} – ${label}` }));
}

/** The three scales of the week feedback, 1 (little) to 5 (a lot), in words. */
export const FEEDBACK_SCALES: {
  field: 'fatigue' | 'motivation' | 'pain';
  label: string;
  choices: { value: number; label: string }[];
}[] = [
  {
    field: 'fatigue',
    label: 'Tiredness',
    choices: scaleChoices(['Fresh', 'Slightly tired', 'Tired', 'Very tired', 'Exhausted']),
  },
  {
    field: 'motivation',
    label: 'Motivation',
    choices: scaleChoices(['Very low', 'Low', 'Okay', 'Good', 'Very high']),
  },
  {
    field: 'pain',
    label: 'Pain',
    choices: scaleChoices(['None', 'Slight', 'Noticeable', 'Strong', 'Severe']),
  },
];

/** The week as a whole, in four steps, from the worst to the best. */
export const VERDICT_CHOICES: { value: WeekVerdict; label: string }[] = [
  { value: 'bad', label: 'Bad' },
  { value: 'fair', label: 'Fair' },
  { value: 'good', label: 'Good' },
  { value: 'strong', label: 'Strong' },
];

const RECOMMENDATION_TEXTS: Record<Recommendation, string> = {
  increase: 'increase the volume a little',
  hold: 'keep the volume about the same',
  reduce: 'reduce the volume',
};

/** What the coach recommends for the next week, in words ("keep the volume about the same"). */
export function recommendationText(recommendation: Recommendation): string {
  return RECOMMENDATION_TEXTS[recommendation];
}
