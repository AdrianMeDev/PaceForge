import {
  EditedSegment,
  EditedWorkout,
  SegmentKind,
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
export const MAX_SEGMENTS = 40;
export const SEGMENT_SECONDS_MAX = 86_400;
export const REPEAT_MAX = 50;

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

const SEGMENT_KIND_LABELS: Record<SegmentKind, string> = {
  warmup: 'Warm-up',
  steady: 'Steady',
  work: 'Work',
  recovery: 'Recovery',
  cooldown: 'Cool-down',
};

export const SPORT_CHOICES: Choice<Sport>[] = choices(SPORT_LABELS);
export const GOAL_CHOICES: Choice<WorkoutGoal>[] = choices(GOAL_LABELS);
export const SEGMENT_KIND_CHOICES: Choice<SegmentKind>[] = choices(SEGMENT_KIND_LABELS);
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

export interface SegmentDraft {
  kind: SegmentKind;
  duration: string;
  repeat: string;
  zone_system: ZoneSystem | '';
  zone: string;
}

export interface SegmentRowError {
  duration?: string;
  repeat?: string;
  zone?: string;
}

export type ParsedSegments =
  | { ok: true; segments: EditedSegment[] }
  | { ok: false; rowErrors: SegmentRowError[]; error: string | null };

/** Seconds ("90"), minutes and seconds ("1:30"), or hours ("1:00:00"), from 1 second to 24 hours. */
export function parseSegmentDuration(text: string): Parsed<number> {
  const trimmed = text.trim();
  const hms = /^(\d{1,2}):([0-5]\d):([0-5]\d)$/.exec(trimmed);
  const ms = /^(\d{1,4}):([0-5]\d)$/.exec(trimmed);
  const seconds = /^\d{1,5}$/.test(trimmed)
    ? Number(trimmed)
    : hms !== null
      ? Number(hms[1]) * 3600 + Number(hms[2]) * 60 + Number(hms[3])
      : ms !== null
        ? Number(ms[1]) * 60 + Number(ms[2])
        : NaN;
  if (Number.isNaN(seconds)) {
    return {
      ok: false,
      error: 'Enter the duration as seconds (90), minutes and seconds (1:30), or hours (1:00:00).',
    };
  }
  if (seconds < 1 || seconds > SEGMENT_SECONDS_MAX) {
    return { ok: false, error: 'Use a duration from 1 second to 24 hours.' };
  }
  return { ok: true, value: seconds };
}

/** Format segment `seconds` as "m:ss" or "h:mm:ss" so `parseSegmentDuration` reads it back. */
export function formatSegmentDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

/** How many times a segment is repeated, from 1 to 50. */
export function parseSegmentRepeat(text: string): Parsed<number> {
  const trimmed = text.trim();
  const repeat = /^\d{1,3}$/.test(trimmed) ? Number(trimmed) : NaN;
  if (Number.isNaN(repeat) || repeat < 1 || repeat > REPEAT_MAX) {
    return { ok: false, error: `Enter whole repeats from 1 to ${REPEAT_MAX}.` };
  }
  return { ok: true, value: repeat };
}

/** A new segment row: 5 minutes of work, repeated once, without a zone target. */
export function blankSegment(): SegmentDraft {
  return {
    kind: 'work',
    duration: '5:00',
    repeat: '1',
    zone_system: '',
    zone: '',
  };
}

/** Turn saved or edited segments into form drafts. */
export function draftsFromSegments(segments: readonly EditedSegment[]): SegmentDraft[] {
  return segments.map((segment) => ({
    kind: segment.kind,
    duration: formatSegmentDuration(segment.seconds),
    repeat: String(segment.repeat),
    zone_system: segment.zone_system ?? '',
    zone: segment.zone === null ? '' : String(segment.zone),
  }));
}

/** Total duration of all segments in seconds, accounting for repeats. */
export function segmentsTotalSeconds(segments: readonly EditedSegment[]): number {
  return segments.reduce((sum, segment) => sum + segment.seconds * segment.repeat, 0);
}

/** Total duration of all segments in whole minutes (at least 1 when non-empty). */
export function segmentsDurationMinutes(segments: readonly EditedSegment[]): number {
  const total = segmentsTotalSeconds(segments);
  return total === 0 ? 0 : Math.max(1, Math.round(total / 60));
}

/** Check that the combined duration of all segments does not exceed 24 hours. */
export function checkSegmentsTotal(segments: readonly EditedSegment[]): string | null {
  if (segmentsTotalSeconds(segments) > SEGMENT_SECONDS_MAX) {
    return 'Segments cannot add up to more than 24 hours.';
  }
  return null;
}

/** Validate and parse all segment drafts, checking row fields, count limit, and 24-hour cap. */
export function parseSegmentDrafts(drafts: readonly SegmentDraft[]): ParsedSegments {
  const rowErrors: SegmentRowError[] = [];
  const segments: EditedSegment[] = [];
  let hasRowError = false;

  for (const draft of drafts) {
    const rowError: SegmentRowError = {};
    const duration = parseSegmentDuration(draft.duration);
    if (!duration.ok) {
      rowError.duration = duration.error;
    }
    const repeat = parseSegmentRepeat(draft.repeat);
    if (!repeat.ok) {
      rowError.repeat = repeat.error;
    }

    let zoneSystem: ZoneSystem | null = null;
    let zone: number | null = null;
    if (draft.zone_system !== '') {
      zoneSystem = draft.zone_system;
      const parsedZone = /^\d+$/.test(draft.zone.trim()) ? Number(draft.zone.trim()) : NaN;
      if (Number.isNaN(parsedZone) || parsedZone < 1 || parsedZone > ZONE_COUNT[zoneSystem]) {
        rowError.zone = 'Choose a zone.';
      } else {
        zone = parsedZone;
      }
    }

    if (
      rowError.duration !== undefined ||
      rowError.repeat !== undefined ||
      rowError.zone !== undefined
    ) {
      hasRowError = true;
    }

    rowErrors.push(rowError);
    if (duration.ok && repeat.ok && rowError.zone === undefined) {
      segments.push({
        kind: draft.kind,
        seconds: duration.value,
        repeat: repeat.value,
        zone_system: zoneSystem,
        zone,
      });
    }
  }

  let error: string | null = null;
  if (drafts.length > MAX_SEGMENTS) {
    error = `Use at most ${MAX_SEGMENTS} segments.`;
  } else if (!hasRowError) {
    error = checkSegmentsTotal(segments);
  }

  if (hasRowError || error !== null) {
    return { ok: false, rowErrors, error };
  }
  return { ok: true, segments };
}

/** Clear zone system and zone on segments whose zone system does not fit `sport`. */
export function sanitizeSegmentZones(
  drafts: readonly SegmentDraft[],
  sport: Sport,
): SegmentDraft[] {
  const allowed = ZONE_SYSTEMS_OF[sport];
  return drafts.map((draft) =>
    draft.zone_system !== '' && !allowed.includes(draft.zone_system)
      ? { ...draft, zone_system: '', zone: '' }
      : { ...draft },
  );
}
