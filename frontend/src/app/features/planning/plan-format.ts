import {
  PlanStatus,
  Segment,
  SegmentKind,
  Sport,
  WorkoutGoal,
  WorkoutSlot,
  ZoneSystem,
  ZoneTarget,
} from '../../core/planning/planning-models';

export const SPORT_LABELS: Record<Sport, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength',
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

/**
 * Where a finding applies, for people: "workouts[2].segments" is "Workout 3", a finding about the
 * whole week (no path) is "Week". Counted in the order the workouts are shown.
 */
export function findingPlace(path: string): string {
  const match = /^workouts\[(\d+)\]/.exec(path);
  return match === null ? 'Week' : `Workout ${Number(match[1]) + 1}`;
}

/** "+ 10 min stretching": what is added to a workout; empty for none. Never a workout. */
export function stretchingText(minutes: number): string {
  return minutes > 0 ? `+ ${minutes} min stretching` : '';
}
