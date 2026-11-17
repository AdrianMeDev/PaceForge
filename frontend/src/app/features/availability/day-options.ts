import { Component, input, model } from '@angular/core';
import { AvailabilitySlot } from '../../core/availability/availability-models';
import { WEEKDAY_NAMES } from './availability-format';

/** The parts of a day, earliest first: the order the server keeps them in. */
export const SLOT_CHOICES: { value: AvailabilitySlot; label: string; short: string }[] = [
  { value: 'morning', label: 'Morning', short: 'Morn.' },
  { value: 'afternoon', label: 'Afternoon', short: 'Aft.' },
  { value: 'evening', label: 'Evening', short: 'Eve.' },
];

export const NO_WINDOW = 'Choose at least one part of the day.';

/** Every weekday allows two sessions and every part of the day until the user says otherwise. */
export const EVERY_DAY_DOUBLE: boolean[] = WEEKDAY_NAMES.map(() => true);
export const EVERY_DAY_OPEN: AvailabilitySlot[][] = WEEKDAY_NAMES.map(() =>
  SLOT_CHOICES.map((choice) => choice.value),
);

/**
 * The message for every weekday that has no part of the day left, `null` for the others. The
 * server refuses the same, with one message for the whole field.
 */
export function windowErrors(windows: readonly (readonly AvailabilitySlot[])[]): (string | null)[] {
  return windows.map((day) => (day.length === 0 ? NO_WINDOW : null));
}

/**
 * Per weekday: whether two sessions are allowed and in which parts of the day training is
 * possible. A part of the form: the page holds the values, checks them with `windowErrors` and
 * saves them with everything else.
 */
@Component({
  selector: 'app-day-options',
  templateUrl: './day-options.html',
  styleUrls: ['../auth/auth-form.css', './day-options.css'],
})
export class DayOptions {
  readonly doubleDays = model.required<boolean[]>();
  readonly timeWindows = model.required<AvailabilitySlot[][]>();
  /** The message for each weekday, `null` where there is none. */
  readonly errors = input<readonly (string | null)[]>([]);

  protected readonly names = WEEKDAY_NAMES;
  protected readonly slots = SLOT_CHOICES;

  protected setDouble(day: number, allowed: boolean): void {
    this.doubleDays.update((flags) => flags.map((old, i) => (i === day ? allowed : old)));
  }

  protected setSlot(day: number, slot: AvailabilitySlot, open: boolean): void {
    this.timeWindows.update((windows) =>
      windows.map((parts, i) =>
        i === day
          ? SLOT_CHOICES.map((choice) => choice.value).filter((part) =>
              part === slot ? open : parts.includes(part),
            )
          : parts,
      ),
    );
  }

  protected isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }
}
