import {
  Assessment,
  AssessmentReason,
  Discipline,
  Goal,
  GoalKind,
  GoalPriority,
  GoalStatus,
  Rating,
} from '../../core/goals/goals-models';
import { formatValue, inputText } from '../athlete/athlete-format';
import { formatDuration } from '../activities/activity-format';

export const KIND_LABELS: Record<GoalKind, string> = {
  race: 'Race',
  threshold: 'Threshold',
  general: 'General',
};

export const DISCIPLINE_LABELS: Record<Discipline, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  triathlon: 'Triathlon',
};

export const PRIORITY_LABELS: Record<GoalPriority, string> = {
  main: 'A · Main goal',
  secondary: 'B · Secondary goal',
  preparation: 'C · Preparation race',
};

export const STATUS_LABELS: Record<GoalStatus, string> = {
  active: 'Active',
  achieved: 'Achieved',
  dropped: 'Dropped',
};

/** `42.2 km`, `5 km`, `800 m`: kilometres with at most one decimal from a kilometre on. */
export function formatGoalDistance(meters: number): string {
  return meters >= 1000 ? `${Number((meters / 1000).toFixed(1))} km` : `${Math.round(meters)} m`;
}

/** "in 12 days", "tomorrow", "today", "yesterday", "3 days ago"; empty for a goal without a date. */
export function daysToGoText(days: number | null): string {
  if (days === null) {
    return '';
  }
  if (days === 0) {
    return 'today';
  }
  if (days === 1) {
    return 'tomorrow';
  }
  if (days === -1) {
    return 'yesterday';
  }
  return days > 0 ? `in ${days} days` : `${-days} days ago`;
}

/**
 * What the goal is aiming for, in one line: a race as "Running · 42.2 km · target 3:45:00", a
 * threshold goal as "FTP 280 W", a general goal as an empty text.
 */
export function describeTarget(goal: Goal): string {
  if (goal.kind === 'race') {
    const parts: string[] = [];
    if (goal.discipline) {
      parts.push(DISCIPLINE_LABELS[goal.discipline]);
    }
    if (goal.distance_m !== null) {
      parts.push(formatGoalDistance(goal.distance_m));
    }
    if (goal.target_time_seconds !== null) {
      parts.push(`target ${formatDuration(goal.target_time_seconds)}`);
    }
    return parts.join(' · ');
  }
  if (goal.kind === 'threshold' && goal.metric && goal.target_value !== null) {
    const label = goal.metric === 'ftp' ? 'FTP' : 'Threshold pace';
    return `${label} ${formatValue(goal.metric, goal.target_value)}`;
  }
  return '';
}

// --- how realistic a goal is

export const RATING_LABELS: Record<Rating, string> = {
  realistic: 'Realistic',
  ambitious: 'Ambitious',
  unrealistic: 'Unrealistic',
  unknown: 'Cannot be judged yet',
};

/** What to do about a goal that could not be judged, by the reason the server gives. */
export const REASON_TEXTS: Record<AssessmentReason, string> = {
  no_model: 'There is no way to judge this kind of goal yet.',
  no_target: 'Give a distance and a target time (or a target value) to see how realistic it is.',
  out_of_range: 'Only running races from 1.5 km to the marathon can be judged.',
  no_date: 'Give a date that has not passed to see how realistic it is.',
  no_form:
    'Enter a recent best time (for a race) or your current value (for FTP or threshold pace) to see how realistic it is.',
};

const JUDGEMENTS: Record<Exclude<Rating, 'unknown'>, string> = {
  realistic: 'Within reach: your form can get there by the date.',
  ambitious: 'A stretch: this asks for a little more than your form is likely to reach by then.',
  unrealistic: 'Out of reach: this asks for much more than your form is likely to reach by then.',
};

function oneDecimal(value: number): string {
  return value.toFixed(1);
}

/**
 * What the judgement says in a sentence, or why there is none. It is a hint: the target stays the
 * athlete's own.
 */
export function judgementText(assessment: Assessment): string {
  if (assessment.rating === 'unknown') {
    return assessment.reason === null ? '' : REASON_TEXTS[assessment.reason];
  }
  return JUDGEMENTS[assessment.rating];
}

/** The numbers behind the judgement: the form now and what the target asks for. */
export function figuresText(goal: Goal): string {
  const { assessment } = goal;
  if (assessment === null || assessment.current === null || assessment.needed === null) {
    return '';
  }
  if (goal.kind === 'race') {
    return `Your running form: VDOT ${oneDecimal(assessment.current)}. The target needs VDOT ${oneDecimal(assessment.needed)}.`;
  }
  if (goal.metric === null) {
    return '';
  }
  const label = goal.metric === 'ftp' ? 'FTP' : 'threshold pace';
  return `Your ${label}: ${formatValue(goal.metric, assessment.current)}. The target: ${formatValue(goal.metric, assessment.needed)}.`;
}

/**
 * The target that can be reached by the date, as text, when it is not the athlete's own (a target
 * that is realistic needs no suggestion); empty otherwise.
 */
export function suggestionText(goal: Goal): string {
  const target = suggestedTarget(goal);
  return target === null ? '' : `A target that can be reached by then: ${target.text}.`;
}

/** The suggested target as text and as it is typed into the field of the form, or `null`. */
export function suggestedTarget(goal: Goal): { text: string; field: string } | null {
  const { assessment } = goal;
  if (
    assessment === null ||
    assessment.suggested === null ||
    (assessment.rating !== 'ambitious' && assessment.rating !== 'unrealistic')
  ) {
    return null;
  }
  if (goal.kind === 'race') {
    const text = formatDuration(assessment.suggested);
    return { text, field: text };
  }
  if (goal.kind === 'threshold' && goal.metric !== null) {
    return {
      text: formatValue(goal.metric, assessment.suggested),
      field: inputText(goal.metric, assessment.suggested),
    };
  }
  return null;
}

/** The warning for a short preparation; empty if there is none. */
export function preparationText(assessment: Assessment): string {
  if (!assessment.prep_short || assessment.weeks === null || assessment.prep_weeks === null) {
    return '';
  }
  const left = assessment.weeks === 1 ? '1 week is' : `${assessment.weeks} weeks are`;
  return `Only ${left} left; a race of this distance should have about ${assessment.prep_weeks} weeks of preparation.`;
}

// --- reading what the user types in the form

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

const TIME_HELP = 'Enter the time as hours, minutes and seconds, for example 3:45:00.';
const TIME_RANGE = 'Enter a time between 1 minute and 100 hours.';
const TARGET_TIME_MIN = 60;
const TARGET_TIME_MAX = 360_000;
const DISTANCE_MAX_KM = 1000;

/**
 * A target time: `3:45:00` (hours, minutes, seconds) or `45:30` (minutes, seconds). Minutes and
 * seconds after a larger unit have two digits and stay below 60. An empty field means no target.
 */
export function parseTargetTime(text: string): Parsed<number | null> {
  const input = text.trim();
  if (!input) {
    return { ok: true, value: null };
  }
  const match = /^(\d{1,3}):(\d{2})(?::(\d{2}))?$/.exec(input);
  if (!match) {
    return { ok: false, error: TIME_HELP };
  }
  const [, first, second, third] = match;
  // With two parts they are minutes and seconds; with three, hours, minutes and seconds.
  const [hours, minutes, seconds] =
    third === undefined
      ? [0, Number(first), Number(second)]
      : [Number(first), Number(second), Number(third)];
  if (seconds >= 60 || (third !== undefined && minutes >= 60)) {
    return { ok: false, error: TIME_HELP };
  }
  const total = hours * 3600 + minutes * 60 + seconds;
  return total >= TARGET_TIME_MIN && total <= TARGET_TIME_MAX
    ? { ok: true, value: total }
    : { ok: false, error: TIME_RANGE };
}

/** A distance in kilometres (a comma works as the decimal point), returned in metres. */
export function parseDistanceKm(text: string): Parsed<number> {
  const input = text.trim();
  if (!input) {
    return { ok: false, error: 'Enter the distance in km.' };
  }
  const normalised = input.replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(normalised)) {
    return { ok: false, error: 'Enter a number, for example 21.1.' };
  }
  const km = Number(normalised);
  return km > 0 && km <= DISTANCE_MAX_KM
    ? { ok: true, value: Math.round(km * 10_000) / 10 }
    : { ok: false, error: `Enter a distance between 0 and ${DISTANCE_MAX_KM} km.` };
}

/** Metres as kilometres for a field: `42.195`, `5`. */
export function kilometresText(meters: number): string {
  return String(Number((meters / 1000).toFixed(4)));
}

export interface DistancePreset {
  label: string;
  meters: number;
}

/** The usual race distances; cycling and swimming events vary too much for a list. */
export const DISTANCE_PRESETS: Record<Discipline, DistancePreset[]> = {
  running: [
    { label: '5 km', meters: 5000 },
    { label: '10 km', meters: 10_000 },
    { label: 'Half marathon', meters: 21_097.5 },
    { label: 'Marathon', meters: 42_195 },
  ],
  triathlon: [
    { label: 'Sprint (25.75 km)', meters: 25_750 },
    { label: 'Olympic (51.5 km)', meters: 51_500 },
    { label: '70.3 (113 km)', meters: 113_000 },
    { label: 'Ironman (226 km)', meters: 226_000 },
  ],
  cycling: [],
  swimming: [],
};
