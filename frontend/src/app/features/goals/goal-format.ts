import {
  Discipline,
  Goal,
  GoalKind,
  GoalPriority,
  GoalStatus,
} from '../../core/goals/goals-models';
import { formatValue } from '../athlete/athlete-format';
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
  main: 'Main goal',
  secondary: 'Secondary goal',
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
