import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { query, settle, typeInto } from '../../testing/dom';
import {
  MINIMUM_ABOVE_BUDGET,
  NO_WISH_TEXTS,
  WeekWishes,
  WishErrors,
  WishTexts,
  readWishes,
} from './week-wishes';

const texts = (given: Partial<WishTexts>): WishTexts => ({ ...NO_WISH_TEXTS, ...given });

describe('readWishes', () => {
  it('reads empty fields as no wish', () => {
    expect(readWishes(NO_WISH_TEXTS, null)).toEqual({
      ok: true,
      value: {
        training_days: null,
        min_weekly_minutes: null,
        long_run_day: null,
        long_ride_day: null,
      },
    });
  });

  it('reads the choices as numbers and the minimum like the budget', () => {
    const result = readWishes(
      texts({ trainingDays: '4', minimum: '5:00', longRunDay: '5', longRideDay: '0' }),
      null,
    );

    expect(result).toEqual({
      ok: true,
      value: {
        training_days: 4,
        min_weekly_minutes: 300,
        long_run_day: 5,
        long_ride_day: 0,
      },
    });
  });

  it('accepts plain minutes and the ends of the lists', () => {
    const result = readWishes(
      texts({ trainingDays: '7', minimum: ' 90 ', longRunDay: '6', longRideDay: '6' }),
      null,
    );

    expect(result).toMatchObject({
      ok: true,
      value: { training_days: 7, min_weekly_minutes: 90, long_run_day: 6, long_ride_day: 6 },
    });
  });

  it('accepts a minimum equal to the budget and any minimum without one', () => {
    expect(readWishes(texts({ minimum: '5:00' }), 300).ok).toBe(true);
    expect(readWishes(texts({ minimum: '100:00' }), null).ok).toBe(true);
  });

  it('refuses a minimum above the budget with the server’s words', () => {
    expect(readWishes(texts({ minimum: '5:01' }), 300)).toEqual({
      ok: false,
      errors: { min_weekly_minutes: MINIMUM_ABOVE_BUDGET },
    });
    expect(MINIMUM_ABOVE_BUDGET).toBe('The minimum cannot be above your weekly budget.');
  });

  it.each(['five', '5:7', '-1', '1.5', '999:00'])('refuses the minimum %j', (minimum) => {
    const result = readWishes(texts({ minimum }), null);

    expect(result.ok).toBe(false);
    expect(result.ok ? [] : Object.keys(result.errors)).toEqual(['min_weekly_minutes']);
  });

  it.each(['0', '8', '10', 'x', '-1'])('refuses %j as a number of days', (trainingDays) => {
    expect(readWishes(texts({ trainingDays }), null)).toEqual({
      ok: false,
      errors: { training_days: 'Choose a number of days from 1 to 7.' },
    });
  });

  it.each(['7', '9', 'Monday'])('refuses %j as a weekday', (day) => {
    const result = readWishes(texts({ longRunDay: day, longRideDay: day }), null);

    expect(result).toEqual({
      ok: false,
      errors: { long_run_day: 'Choose a weekday.', long_ride_day: 'Choose a weekday.' },
    });
  });

  it('names every field that is wrong at once', () => {
    const result = readWishes(
      texts({ trainingDays: '9', minimum: 'x', longRunDay: '9', longRideDay: '9' }),
      null,
    );

    expect(result.ok ? [] : Object.keys(result.errors)).toEqual([
      'training_days',
      'long_run_day',
      'long_ride_day',
      'min_weekly_minutes',
    ]);
  });
});

@Component({
  imports: [WeekWishes],
  template: `<app-week-wishes [(wishes)]="wishes" [errors]="errors()" />`,
})
class Host {
  readonly wishes = signal<WishTexts>(NO_WISH_TEXTS);
  readonly errors = signal<WishErrors>({});
}

describe('WeekWishes', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let element: HTMLElement;

  beforeEach(async () => {
    TestBed.configureTestingModule({ imports: [Host] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    element = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  });

  const select = (id: string) => query<HTMLSelectElement>(element, `#${id}`);

  async function choose(id: string, value: string): Promise<void> {
    const box = select(id);
    box.value = value;
    box.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  it('offers no wish first, then one to seven days and the seven weekdays', () => {
    expect(Array.from(select('wish-training-days').options).map((o) => o.value)).toEqual([
      '',
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
    ]);
    expect(Array.from(select('wish-long-run').options).map((o) => o.textContent?.trim())).toEqual([
      'No wish',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ]);
    expect(select('wish-training-days').value).toBe('');
  });

  it('shows the values it is given', async () => {
    host.wishes.set(
      texts({ trainingDays: '4', minimum: '5:00', longRunDay: '5', longRideDay: '6' }),
    );
    await settle(fixture);

    expect(select('wish-training-days').value).toBe('4');
    expect(query<HTMLInputElement>(element, '#wish-minimum').value).toBe('5:00');
    expect(select('wish-long-run').value).toBe('5');
    expect(select('wish-long-ride').value).toBe('6');
  });

  it('hands every change to the page, field by field', async () => {
    await choose('wish-training-days', '3');
    await choose('wish-long-run', '5');
    await choose('wish-long-ride', '6');
    typeInto(element, '#wish-minimum', '4:30');
    await settle(fixture);

    expect(host.wishes()).toEqual({
      trainingDays: '3',
      minimum: '4:30',
      longRunDay: '5',
      longRideDay: '6',
    });
  });

  it('takes a choice back with no wish', async () => {
    host.wishes.set(texts({ longRunDay: '5' }));
    await settle(fixture);

    await choose('wish-long-run', '');

    expect(host.wishes().longRunDay).toBe('');
  });

  it('shows a message next to its field and marks the field', async () => {
    host.errors.set({
      min_weekly_minutes: MINIMUM_ABOVE_BUDGET,
      long_run_day: 'Choose a weekday.',
    });
    await settle(fixture);

    const alerts = Array.from(element.querySelectorAll('[role="alert"]')).map((e) =>
      e.textContent?.trim(),
    );
    expect(alerts).toEqual([MINIMUM_ABOVE_BUDGET, 'Choose a weekday.']);
    expect(query(element, '#wish-minimum').getAttribute('aria-invalid')).toBe('true');
    expect(select('wish-long-run').getAttribute('aria-invalid')).toBe('true');
    expect(select('wish-long-ride').getAttribute('aria-invalid')).toBeNull();
  });
});
