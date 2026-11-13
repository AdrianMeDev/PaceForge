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
