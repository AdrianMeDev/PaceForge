import { PeriodKind } from '../../core/availability/availability-models';
import { Parsed } from '../goals/goal-format';

export const WEEKDAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

/** The server's limits: a day has 24 hours, a week 168. */
export const DAY_MAX_MINUTES = 1440;
export const WEEK_MAX_MINUTES = 10080;

const HELP = 'Enter minutes (90) or hours and minutes (1:30).';

/** `1:30` for 90 minutes, `0:00` for none, `10:30` for 630. */
export function formatMinutes(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

/**
 * Minutes as people type them: a plain number is minutes (`90`), `h:mm` is hours and minutes
 * (`1:30`, the minutes always with two digits and below 60). At most `max` minutes. The caller
 * decides what an empty field means.
 */
export function parseMinutes(text: string, max: number): Parsed<number> {
  const match = /^(?:(\d{1,3}):([0-5]\d)|(\d{1,5}))$/.exec(text.trim());
  if (!match) {
    return { ok: false, error: HELP };
  }
  const [, hours, minutes, plain] = match;
  const total = plain === undefined ? Number(hours) * 60 + Number(minutes) : Number(plain);
  return total <= max
    ? { ok: true, value: total }
    : { ok: false, error: `Enter at most ${formatMinutes(max)} (${max} minutes).` };
}

// --- periods of absence

export const PERIOD_KIND_LABELS: Record<PeriodKind, string> = {
  vacation: 'Vacation',
  illness: 'Illness',
  other: 'Other',
};

/** The longest period the server takes, both ends included. */
export const PERIOD_MAX_DAYS = 366;

const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 24 * 60 * 60 * 1000;

/** `2027-07-12` that is a day of the calendar (not `2027-02-30`). */
export function isCalendarDate(text: string): boolean {
  return dayNumber(text) !== null;
}

/** How many days lie from `start` to `end`, both included; `null` if either is no date. */
export function inclusiveDays(start: string, end: string): number | null {
  const first = dayNumber(start);
  const last = dayNumber(end);
  return first === null || last === null ? null : last - first + 1;
}

/** `1 day`, `14 days`. */
export function formatPeriodLength(days: number): string {
  return days === 1 ? '1 day' : `${days} days`;
}

/** Days since 1970-01-01 of a calendar date given as text, or `null`. */
function dayNumber(text: string): number | null {
  if (!CALENDAR_DATE.test(text)) {
    return null;
  }
  const time = Date.parse(`${text}T00:00:00Z`);
  // A date that does not exist is rolled over by some parsers; this one must read back the same.
  if (Number.isNaN(time) || new Date(time).toISOString().slice(0, 10) !== text) {
    return null;
  }
  return time / DAY_MS;
}
