import { Sport } from '../../core/activities/activities-models';
import { Parsed } from '../goals/goal-format';

export const DURATION_MAX_MINUTES = 1440;
export const DISTANCE_MAX_KM = 1000;
export const NOTES_MAX = 500;

export const SPORT_CHOICES: { value: Sport; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'cycling', label: 'Cycling' },
  { value: 'swimming', label: 'Swimming' },
  { value: 'strength', label: 'Strength' },
  { value: 'other', label: 'Other' },
];

/** The scale of perceived exertion, 1 to 10, in words that say what the numbers are. */
export const RPE_CHOICES: { value: number; label: string }[] = [
  'Very easy',
  'Easy',
  'Moderate',
  'Somewhat hard',
  'Hard',
  'Harder',
  'Very hard',
  'Very, very hard',
  'Almost maximal',
  'Maximal',
].map((words, index) => ({ value: index + 1, label: `${index + 1} – ${words}` }));

const DIGITS = /^\d+$/;
const DECIMAL = /^\d+([.,]\d{1,3})?$/;

/** Whole minutes, 1 to a day. */
export function parseDuration(text: string): Parsed<number> {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { ok: false, error: 'Enter how long the session was, in minutes.' };
  }
  const minutes = DIGITS.test(trimmed) ? Number(trimmed) : NaN;
  if (!Number.isSafeInteger(minutes) || minutes < 1 || minutes > DURATION_MAX_MINUTES) {
    return { ok: false, error: `Enter whole minutes from 1 to ${DURATION_MAX_MINUTES}.` };
  }
  return { ok: true, value: minutes };
}

/** Kilometres with a point or a comma, up to 1000; empty is fine and means no distance. */
export function parseDistance(text: string): Parsed<number | null> {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { ok: true, value: null };
  }
  const km = DECIMAL.test(trimmed) ? Number(trimmed.replace(',', '.')) : NaN;
  if (!Number.isFinite(km) || km > DISTANCE_MAX_KM) {
    return { ok: false, error: `Enter kilometres from 0 to ${DISTANCE_MAX_KM}, such as 5.5.` };
  }
  return { ok: true, value: km };
}

/** The day on the clock of the user, `YYYY-MM-DD`. */
export function todayText(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** The time on the clock of the user, `HH:MM`. */
export function timeText(now: Date = new Date()): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}
