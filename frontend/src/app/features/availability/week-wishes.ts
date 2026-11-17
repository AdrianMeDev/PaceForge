import { Component, input, model } from '@angular/core';
import { WEEKDAY_NAMES, WEEK_MAX_MINUTES, parseMinutes } from './availability-format';

/** What the user typed or chose: empty means no wish. */
export interface WishTexts {
  trainingDays: string;
  minimum: string;
  longRunDay: string;
  longRideDay: string;
}
export type WishName = 'training_days' | 'min_weekly_minutes' | 'long_run_day' | 'long_ride_day';
/** Messages by field, as the server names the fields. */
export type WishErrors = Partial<Record<WishName, string>>;

export interface Wishes {
  training_days: number | null;
  min_weekly_minutes: number | null;
  long_run_day: number | null;
  long_ride_day: number | null;
}

export const NO_WISH_TEXTS: WishTexts = {
  trainingDays: '',
  minimum: '',
  longRunDay: '',
  longRideDay: '',
};
export const WISH_FIELDS: readonly WishName[] = [
  'training_days',
  'min_weekly_minutes',
  'long_run_day',
  'long_ride_day',
];

/** The server's message for a minimum above the budget. */
export const MINIMUM_ABOVE_BUDGET = 'The minimum cannot be above your weekly budget.';

/**
 * The wishes as numbers (`null` for an empty field), or the messages by field. The minimum is
 * typed like the budget (`5:00`) and must not be above it; the days are chosen from a list, so
 * only a value the list does not offer is refused.
 */
export function readWishes(
  texts: WishTexts,
  budget: number | null,
): { ok: true; value: Wishes } | { ok: false; errors: WishErrors } {
  const errors: WishErrors = {};
  const days = chosen(texts.trainingDays, 1, 7);
  if (days === undefined) {
    errors.training_days = 'Choose a number of days from 1 to 7.';
  }
  const run = chosen(texts.longRunDay, 0, 6);
  if (run === undefined) {
    errors.long_run_day = 'Choose a weekday.';
  }
  const ride = chosen(texts.longRideDay, 0, 6);
  if (ride === undefined) {
    errors.long_ride_day = 'Choose a weekday.';
  }
  let minimum: number | null = null;
  const typed = texts.minimum.trim();
  if (typed !== '') {
    const parsed = parseMinutes(typed, WEEK_MAX_MINUTES);
    if (!parsed.ok) {
      errors.min_weekly_minutes = parsed.error;
    } else if (budget !== null && parsed.value > budget) {
      errors.min_weekly_minutes = MINIMUM_ABOVE_BUDGET;
    } else {
      minimum = parsed.value;
    }
  }
  if (Object.keys(errors).length) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    value: {
      training_days: days ?? null,
      min_weekly_minutes: minimum,
      long_run_day: run ?? null,
      long_ride_day: ride ?? null,
    },
  };
}

/** `null` for no choice, a whole number in range, `undefined` for anything else. */
function chosen(text: string, low: number, high: number): number | null | undefined {
  if (text === '') {
    return null;
  }
  const value = /^\d$/.test(text) ? Number(text) : NaN;
  return value >= low && value <= high ? value : undefined;
}

/**
 * The wishes for a week: on how many days to train at most, the least to train in a week, and the
 * weekday of the long run and of the long ride. A part of the availability form: the page holds
 * the values, checks them with `readWishes` and saves them with everything else.
 */
@Component({
  selector: 'app-week-wishes',
  templateUrl: './week-wishes.html',
  styleUrl: './week-wishes.css',
})
export class WeekWishes {
  readonly wishes = model.required<WishTexts>();
  readonly errors = input<WishErrors>({});

  protected readonly dayCounts = [1, 2, 3, 4, 5, 6, 7];
  protected readonly weekdays = WEEKDAY_NAMES.map((name, index) => ({ value: index, name }));

  protected set(name: keyof WishTexts, event: Event): void {
    const text = (event.target as HTMLInputElement | HTMLSelectElement).value;
    this.wishes.update((old) => ({ ...old, [name]: text }));
  }
}
