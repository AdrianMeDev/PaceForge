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
