import {
  Exercise,
  ExerciseEquipment,
  ExerciseRegion,
  ExportSummary,
  PlanStatus,
  PushOutcome,
  Segment,
  SegmentKind,
  Severity,
  Sport,
  WorkoutExport,
  WorkoutGoal,
  WorkoutSlot,
  ZoneSystem,
  ZoneTarget,
} from '../../core/planning/planning-models';
import { IconName } from '../../shared/icon';

export const SPORT_LABELS: Record<Sport, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength',
};

/** The icon of a sport; `other` is an activity that was not planned as one of the four. */
export const SPORT_ICONS: Record<Sport | 'other', IconName> = {
  running: 'running',
  cycling: 'bike',
  swimming: 'waves',
  strength: 'dumbbell',
  other: 'activity',
};

export const GOAL_LABELS: Record<WorkoutGoal, string> = {
  recovery: 'Recovery',
  endurance: 'Endurance',
  tempo: 'Tempo',
  threshold: 'Threshold',
  vo2max: 'VO2max',
  strength: 'Strength',
  other: 'Other',
};

export const STATUS_LABELS: Record<PlanStatus, string> = {
  draft: 'Draft',
  confirmed: 'Confirmed',
  superseded: 'Replaced',
  discarded: 'Discarded',
};

export const SLOT_LABELS: Record<WorkoutSlot, string> = {
  morning: 'Morning',
  afternoon: 'Afternoon',
  evening: 'Evening',
};

const ZONE_SYSTEM_LABELS: Record<ZoneSystem, string> = {
  power: 'Power',
  heart_rate: 'Heart rate',
  pace: 'Pace',
};

const SEGMENT_LABELS: Record<SegmentKind, string> = {
  warmup: 'warm-up',
  steady: 'steady',
  work: 'work',
  recovery: 'recovery',
  cooldown: 'cool-down',
};

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * A calendar date (YYYY-MM-DD) as day number, month number and weekday, computed in UTC so that
 * the time zone of the browser cannot move it to another day.
 */
function parts(date: string): { day: number; month: number; weekday: number } {
  const [year, month, day] = date.split('-').map(Number);
  const time = new Date(Date.UTC(year, month - 1, day));
  return { day: time.getUTCDate(), month: time.getUTCMonth(), weekday: time.getUTCDay() };
}

/** "Mon 16 Nov": the weekday and the date of a day of a plan. */
export function dayLabel(date: string): string {
  const { day, month, weekday } = parts(date);
  return `${WEEKDAYS[weekday]} ${day} ${MONTHS[month]}`;
}

/** The longest note a user may give the coach for a week (as on the server). */
export const WEEK_NOTE_MAX = 300;

/** The Monday a week after the given one, YYYY-MM-DD. */
export function weekAfter(monday: string): string {
  const [year, month, day] = monday.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + 7)).toISOString().slice(0, 10);
}

/** "16 Nov – 22 Nov": the week that starts on the given Monday, Sunday included. */
export function weekRange(monday: string): string {
  const [year, month, day] = monday.split('-').map(Number);
  const sunday = new Date(Date.UTC(year, month - 1, day + 6));
  const start = parts(monday);
  return `${start.day} ${MONTHS[start.month]} – ${sunday.getUTCDate()} ${MONTHS[sunday.getUTCMonth()]}`;
}

/** "45 min", "1 h", "1 h 30 min": the length of a workout. */
export function minutesText(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) {
    return `${rest} min`;
  }
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** Unified load points, for workout estimates and week totals. */
export function loadText(load: number): string {
  return `${load} pts`;
}

/** "138–188 W", "145–152 bpm", "4:20–4:45 /km": the numbers of a zone; empty without a range. */
export function rangeText(range: ZoneTarget | null): string {
  if (range === null) {
    return '';
  }
  if (range.unit === 's/km') {
    return `${paceText(range.low)}–${paceText(range.high)} /km`;
  }
  return `${range.low}–${range.high} ${range.unit}`;
}

function paceText(secondsPerKm: number): string {
  const seconds = secondsPerKm % 60;
  return `${Math.floor(secondsPerKm / 60)}:${seconds < 10 ? '0' : ''}${seconds}`;
}

/** "Power zone 2" or "Power zone 2 · 138–188 W"; empty without a target. */
export function targetText(
  system: ZoneSystem | null,
  zone: number | null,
  range: ZoneTarget | null = null,
): string {
  if (system === null || zone === null) {
    return '';
  }
  const text = `${ZONE_SYSTEM_LABELS[system]} zone ${zone}`;
  return range === null ? text : `${text} · ${rangeText(range)}`;
}

/** "3 × 10 min work, power zone 4", "15 min warm-up": one part of an interval workout. */
export function segmentText(segment: Segment): string {
  const total = segment.seconds;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  const length =
    minutes === 0
      ? `${seconds} s`
      : seconds === 0
        ? `${minutes} min`
        : `${minutes} min ${seconds} s`;
  const repeat = segment.repeat > 1 ? `${segment.repeat} × ` : '';
  const target = targetText(segment.zone_system, segment.zone, segment.target);
  const text = `${repeat}${length} ${SEGMENT_LABELS[segment.kind]}`;
  return target === '' ? text : `${text}, ${target.charAt(0).toLowerCase()}${target.slice(1)}`;
}

/** What the checks found in a line: "1 error, 2 notes". */
export function findingsSummary(findings: { severity: Severity }[]): string {
  const errors = findings.filter((finding) => finding.severity === 'error').length;
  const notes = findings.length - errors;
  const parts: string[] = [];
  if (errors > 0) {
    parts.push(errors === 1 ? '1 error' : `${errors} errors`);
  }
  if (notes > 0) {
    parts.push(notes === 1 ? '1 note' : `${notes} notes`);
  }
  return parts.join(', ');
}

/**
 * Where a finding applies, for people: "workouts[2].segments" is "Workout 3", a finding about the
 * whole week (no path) is "Week". Counted in the order the workouts are shown.
 */
export function findingPlace(path: string): string {
  const match = /^workouts\[(\d+)\]/.exec(path);
  return match === null ? 'Week' : `Workout ${Number(match[1]) + 1}`;
}

export const REGION_LABELS: Record<ExerciseRegion, string> = {
  legs: 'Legs',
  core: 'Core',
  upper_body: 'Upper body',
  full_body: 'Full body',
};

export const EQUIPMENT_LABELS: Record<ExerciseEquipment, string> = {
  gym: 'Gym',
  dumbbells: 'Dumbbells',
  bodyweight: 'Body weight',
};

/**
 * "3 × 10 · RPE 7 · rest 1:30", "3 × 45 s": the numbers of an exercise (the name is shown next
 * to it). Sets of repetitions or of a hold, then the RPE and the rest if they are given.
 */
export function exerciseDetail(exercise: Exercise): string {
  const amount = exercise.reps !== null ? `${exercise.reps}` : `${exercise.seconds ?? 0} s`;
  const parts = [`${exercise.sets} × ${amount}`];
  if (exercise.rpe !== null) {
    parts.push(`RPE ${exercise.rpe}`);
  }
  if (exercise.rest_seconds !== null) {
    const rest = exercise.rest_seconds;
    parts.push(`rest ${Math.floor(rest / 60)}:${String(rest % 60).padStart(2, '0')}`);
  }
  return parts.join(' · ');
}

/** "+ 10 min stretching": what is added to a workout; empty for none. Never a workout. */
export function stretchingText(minutes: number): string {
  return minutes > 0 ? `+ ${minutes} min stretching` : '';
}

const EXPORT_ERRORS = {
  rejected: 'Intervals.icu did not accept this workout.',
  unavailable: 'Intervals.icu could not be reached.',
  unexpected: 'Intervals.icu answered in an unexpected way.',
} as const;

function count(amount: number, one: string, many: string): string {
  return `${amount} ${amount === 1 ? one : many}`;
}

/** Where one workout stands: "In Intervals.icu", "Not sent yet" or why it failed. */
export function exportText(state: WorkoutExport): string {
  switch (state.status) {
    case 'synced':
      return 'In Intervals.icu';
    case 'failed':
      return `Not sent: ${state.error_code === '' ? EXPORT_ERRORS.unexpected : EXPORT_ERRORS[state.error_code]}`;
    default:
      return 'Not sent to Intervals.icu yet';
  }
}

/** How the week stands with Intervals.icu, in a sentence or two. */
export function exportSummaryText(summary: ExportSummary): string {
  const total = summary.synced + summary.failed + summary.not_sent;
  const parts: string[] = [];
  if (total > 0 && summary.not_sent === total) {
    parts.push('Not sent to Intervals.icu yet.');
  } else if (total > 0) {
    parts.push(`${summary.synced} of ${count(total, 'workout', 'workouts')} in Intervals.icu.`);
    if (summary.failed > 0) {
      parts.push(`${summary.failed} could not be sent.`);
    }
    if (summary.not_sent > 0) {
      parts.push(`${summary.not_sent} not sent yet.`);
    }
  }
  if (summary.older > 0) {
    parts.push('Events of an older version are still in Intervals.icu; sending replaces them.');
  }
  return parts.join(' ');
}

/** What a push did, for the notice above the plan. */
export function pushText(outcome: PushOutcome): string {
  if (!outcome.ok) {
    return outcome.message;
  }
  const parts: string[] = [];
  if (outcome.synced > 0) {
    parts.push(`${count(outcome.synced, 'workout was', 'workouts were')} sent to Intervals.icu.`);
  }
  if (outcome.failed > 0) {
    parts.push(`${count(outcome.failed, 'workout', 'workouts')} could not be sent.`);
  }
  if (outcome.removed > 0) {
    parts.push(`${count(outcome.removed, 'event', 'events')} of an older version removed.`);
  }
  if (outcome.left_behind > 0) {
    parts.push(`${count(outcome.left_behind, 'event', 'events')} could not be removed yet.`);
  }
  return parts.length === 0 ? 'There was nothing to send.' : parts.join(' ');
}
