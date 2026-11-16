import { BestTime, BestTimeDistance, BestTimeInput } from '../../core/athlete/athlete-models';
import { formatDuration } from '../activities/activity-format';
import { Parsed, parseTargetTime } from '../goals/goal-format';

/** The distances of the best times, shortest first (as the server lists them). */
export const DISTANCE_LABELS: Record<BestTimeDistance, string> = {
  '5k': '5 km',
  '10k': '10 km',
  half_marathon: 'Half marathon',
  marathon: 'Marathon',
};

export const DISTANCES = Object.keys(DISTANCE_LABELS) as BestTimeDistance[];

/** The earliest day of a race that the server takes. */
export const EARLIEST_DAY = '1900-01-01';

const TIME_REQUIRED = 'Enter your time, for example 19:57 or 1:35:00.';
const DAY_REQUIRED = 'Enter the day of the race.';

/** What the user typed for one distance. */
export interface BestTimeDraft {
  time: string;
  date: string;
}

/** The draft of what is stored; empty for a distance without a time. */
export function draftOf(stored: BestTime | null): BestTimeDraft {
  return stored === null
    ? { time: '', date: '' }
    : { time: formatDuration(stored.seconds), date: stored.date };
}

/**
 * What to send for a draft, or the messages of the fields that cannot be used. The time is
 * `19:57` or `1:35:00`; the day is `YYYY-MM-DD`, not before 1900 and not after ``today``.
 * @param today the day of today in the same form, which is the latest day of a race.
 */
export function inputOf(
  draft: BestTimeDraft,
  today: string,
): Parsed<BestTimeInput> | { ok: false; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const time = draft.time.trim() ? parseTargetTime(draft.time) : null;
  if (time === null) {
    errors['seconds'] = TIME_REQUIRED;
  } else if (!time.ok) {
    errors['seconds'] = time.error;
  }
  const date = draft.date.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(date))) {
    errors['date'] = DAY_REQUIRED;
  } else if (date < EARLIEST_DAY || date > today) {
    errors['date'] = 'Enter the day of the race: not in the future, not before 1900.';
  }
  if (Object.keys(errors).length || time === null || !time.ok || time.value === null) {
    return { ok: false, errors };
  }
  return { ok: true, value: { seconds: time.value, date } };
}

/** The day of today on this device as `YYYY-MM-DD`. */
export function todayText(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** What a stored time means for the threshold pace, in a few words. */
export function standing(stored: BestTime): string {
  if (stored.counts) {
    return 'This one gives your threshold pace.';
  }
  return stored.recent
    ? 'A newer race gives your threshold pace.'
    : 'More than a year ago: too old to count.';
}
