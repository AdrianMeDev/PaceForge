import {
  EditedSegment,
  EditedWorkout,
  Sport,
  Workout,
  WorkoutGoal,
  WorkoutSlot,
  ZoneSystem,
} from '../../core/planning/planning-models';
import { GOAL_LABELS, SLOT_LABELS, SPORT_LABELS, dayLabel } from './plan-format';

/** The limits of the server (`planning/schema.py`), checked here so that a message stands next to its field. */
export const TITLE_MAX = 100;
export const NOTES_MAX = 500;
export const DURATION_MAX = 1440;
export const STRETCHING_MAX = 60;

/** How many zones a system has: the seven power levels, five heart rate zones, five pace zones. */
export const ZONE_COUNT: Record<ZoneSystem, number> = { power: 7, heart_rate: 5, pace: 5 };

const ZONE_SYSTEM_LABELS: Record<ZoneSystem, string> = {
  power: 'Power',
  heart_rate: 'Heart rate',
  pace: 'Pace',
};

/** The zone systems that make sense for a sport; swimming and strength have none. */
export const ZONE_SYSTEMS_OF: Record<Sport, ZoneSystem[]> = {
  running: ['pace', 'heart_rate'],
  cycling: ['power', 'heart_rate'],
  swimming: [],
  strength: [],
};

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

export interface Choice<T extends string> {
  value: T;
  label: string;
}

function choices<T extends string>(labels: Record<T, string>): Choice<T>[] {
  return (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));
}

export const SPORT_CHOICES: Choice<Sport>[] = choices(SPORT_LABELS);
export const GOAL_CHOICES: Choice<WorkoutGoal>[] = choices(GOAL_LABELS);
/** The times of day, and "no time" first: only the order is meant, there is no clock time. */
export const SLOT_CHOICES: Choice<WorkoutSlot | ''>[] = [
  { value: '', label: 'Not said' },
  ...choices(SLOT_LABELS),
];

export function zoneSystemChoices(sport: Sport): Choice<ZoneSystem>[] {
  return ZONE_SYSTEMS_OF[sport].map((value) => ({ value, label: ZONE_SYSTEM_LABELS[value] }));
}

/** "Zone 1" to the last zone of the system. */
export function zoneChoices(system: ZoneSystem): { value: number; label: string }[] {
  return Array.from({ length: ZONE_COUNT[system] }, (_, index) => ({
    value: index + 1,
    label: `Zone ${index + 1}`,
  }));
}

/** The date `days` after `date` (both `YYYY-MM-DD`), counted in UTC so that no time zone moves it. */
export function addDays(date: string, days: number): string {
  const [year, month, day] = date.split('-').map(Number);
  const moved = new Date(Date.UTC(year, month - 1, day + days));
  const text = (value: number) => String(value).padStart(2, '0');
  return `${moved.getUTCFullYear()}-${text(moved.getUTCMonth() + 1)}-${text(moved.getUTCDate())}`;
}

/** The seven days of the week that starts on `monday`, as "Mon 16 Nov". */
export function dayChoices(monday: string): Choice<string>[] {
  return Array.from({ length: 7 }, (_, index) => {
    const value = addDays(monday, index);
    return { value, label: dayLabel(value) };
  });
}

/** Minutes ("90") or hours and minutes ("1:30"), from a minute to a day. */
export function parseDuration(text: string): Parsed<number> {
  const trimmed = text.trim();
  const hours = /^(\d{1,2}):([0-5]\d)$/.exec(trimmed);
  const minutes = /^\d{1,4}$/.test(trimmed)
    ? Number(trimmed)
    : hours === null
      ? NaN
      : Number(hours[1]) * 60 + Number(hours[2]);
  if (Number.isNaN(minutes)) {
    return { ok: false, error: 'Enter the duration as minutes (90) or hours and minutes (1:30).' };
  }
  if (minutes < 1 || minutes > DURATION_MAX) {
    return { ok: false, error: 'Use a duration from 1 minute to 24 hours.' };
  }
  return { ok: true, value: minutes };
}

/** Minutes of stretching, 0 to an hour; empty means none. */
export function parseStretching(text: string): Parsed<number> {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { ok: true, value: 0 };
  }
  const minutes = /^\d{1,3}$/.test(trimmed) ? Number(trimmed) : NaN;
  if (Number.isNaN(minutes) || minutes > STRETCHING_MAX) {
    return { ok: false, error: `Enter whole minutes from 0 to ${STRETCHING_MAX}.` };
  }
  return { ok: true, value: minutes };
}

/** A title is one line of text of 1 to 100 characters (checked after trimming, as the server does). */
export function checkTitle(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === '') {
    return 'Enter a title.';
  }
  if (trimmed.length > TITLE_MAX) {
    return `Use at most ${TITLE_MAX} characters.`;
  }
  // Control characters (line breaks too) and the line and paragraph separators.
  if (/[\p{Cc}\p{Zl}\p{Zp}]/u.test(trimmed)) {
    return 'A title is one line of plain text.';
  }
  return null;
}

/** Notes may have several lines, and nothing else that is invisible. */
export function checkNotes(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed.length > NOTES_MAX) {
    return `Use at most ${NOTES_MAX} characters.`;
  }
  // Every control character except the line break, and the line and paragraph separators.
  if (/[^\P{Cc}\n]|[\p{Zl}\p{Zp}]/u.test(trimmed)) {
    return 'Notes are plain text.';
  }
  return null;
}

/**
 * A workout of a plan as it is sent back when the plan is changed: with its lineage and without
 * what the server works out (`target`) or knows (`export`).
 */
export function editedFrom(workout: Workout): EditedWorkout {
  return {
    lineage: workout.lineage,
    day: workout.day,
    sport: workout.sport,
    title: workout.title,
    goal: workout.goal,
    duration_minutes: workout.duration_minutes,
    zone_system: workout.zone_system,
    zone: workout.zone,
    notes: workout.notes,
    slot: workout.slot,
    stretching_minutes: workout.stretching_minutes,
    segments: workout.segments.map((segment): EditedSegment => ({
      kind: segment.kind,
      seconds: segment.seconds,
      repeat: segment.repeat,
      zone_system: segment.zone_system,
      zone: segment.zone,
    })),
    exercises: workout.exercises.map((exercise) => ({ ...exercise })),
  };
}

/** What a new workout starts as: an easy hour of running on `day`. */
export function blankWorkout(day: string): EditedWorkout {
  return {
    lineage: null,
    day,
    sport: 'running',
    title: '',
    goal: 'endurance',
    duration_minutes: 60,
    zone_system: null,
    zone: null,
    notes: '',
    slot: null,
    stretching_minutes: 0,
    segments: [],
    exercises: [],
  };
}

/** A workout of the plan that is being changed, with its place in the list that is sent. */
export interface EditorItem {
  index: number;
  workout: EditedWorkout;
}

/** The workouts of one day, in the order the server stores them in. */
export interface EditorDay {
  date: string;
  label: string;
  items: EditorItem[];
}

const SLOT_RANK: Record<WorkoutSlot, number> = { morning: 0, afternoon: 1, evening: 2 };

/**
 * The workouts by day, each day in the order of the times of day (a workout without one last, and
 * otherwise as they are in the list): the order of the server, so that "Workout 3" in a finding is
 * the third one shown.
 */
export function editorDays(workouts: readonly EditedWorkout[]): EditorDay[] {
  const items = workouts
    .map((workout, index) => ({ index, workout }))
    .sort(
      (a, b) =>
        a.workout.day.localeCompare(b.workout.day) ||
        rank(a.workout.slot) - rank(b.workout.slot) ||
        a.index - b.index,
    );
  const days: EditorDay[] = [];
  for (const item of items) {
    let day = days.find((candidate) => candidate.date === item.workout.day);
    if (day === undefined) {
      day = { date: item.workout.day, label: dayLabel(item.workout.day), items: [] };
      days.push(day);
    }
    day.items.push(item);
  }
  return days;
}

function rank(slot: WorkoutSlot | null): number {
  return slot === null ? 3 : SLOT_RANK[slot];
}

/** How many parts the interval structure of a workout has, in words; empty without one. */
export function structureText(workout: EditedWorkout): string {
  const parts = workout.segments.length;
  return parts === 0 ? '' : `Interval structure with ${parts} ${parts === 1 ? 'part' : 'parts'}`;
}
