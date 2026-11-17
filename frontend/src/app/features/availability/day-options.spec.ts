import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AvailabilitySlot } from '../../core/availability/availability-models';
import { query, settle } from '../../testing/dom';
import {
  DayOptions,
  EVERY_DAY_DOUBLE,
  EVERY_DAY_OPEN,
  NO_WINDOW,
  windowErrors,
} from './day-options';

describe('windowErrors', () => {
  it('names only the weekdays that have no part of the day', () => {
    const windows: AvailabilitySlot[][] = [['morning'], [], ['evening', 'morning'], []];

    expect(windowErrors(windows)).toEqual([null, NO_WINDOW, null, NO_WINDOW]);
  });

  it('has nothing to say when every day is open', () => {
    expect(windowErrors(EVERY_DAY_OPEN).every((message) => message === null)).toBe(true);
  });
});

describe('the defaults', () => {
  it('are two sessions and every part of the day on all seven weekdays', () => {
    expect(EVERY_DAY_DOUBLE).toEqual(Array(7).fill(true));
    expect(EVERY_DAY_OPEN).toHaveLength(7);
    expect(EVERY_DAY_OPEN.every((day) => day.join() === 'morning,afternoon,evening')).toBe(true);
  });
});

@Component({
  imports: [DayOptions],
  template: `<app-day-options
    [(doubleDays)]="doubleDays"
    [(timeWindows)]="timeWindows"
    [errors]="errors()"
  />`,
})
class Host {
  readonly doubleDays = signal<boolean[]>([...EVERY_DAY_DOUBLE]);
  readonly timeWindows = signal<AvailabilitySlot[][]>(EVERY_DAY_OPEN.map((day) => [...day]));
  readonly errors = signal<(string | null)[]>([]);
}

describe('DayOptions', () => {
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

  const box = (id: string) => query<HTMLInputElement>(element, `#${id}`);

  async function click(id: string): Promise<void> {
    box(id).click();
    await settle(fixture);
  }

  it('gives every column a short head for a phone and the whole text for assistive technology', () => {
    const heads = Array.from(element.querySelectorAll('thead th')).map((th) => ({
      long: th.querySelector('span:not([aria-hidden])')?.textContent?.trim(),
      short: th.querySelector('span[aria-hidden="true"]')?.textContent?.trim(),
    }));

    expect(heads.slice(1)).toEqual([
      { long: 'Morning', short: 'Morn.' },
      { long: 'Afternoon', short: 'Aft.' },
      { long: 'Evening', short: 'Eve.' },
      { long: 'Two sessions', short: '2×' },
    ]);
  });

  it('has a row for every weekday with the three parts of the day and two sessions', () => {
    const rows = Array.from(element.querySelectorAll('tbody tr'));

    expect(rows).toHaveLength(7);
    expect(rows[0].querySelector('th')?.textContent?.trim()).toBe('Monday');
    expect(rows[6].querySelector('th')?.textContent?.trim()).toBe('Sunday');
    expect(rows[0].querySelectorAll('input[type="checkbox"]')).toHaveLength(4);
  });

  it('names every box for a screen reader', () => {
    expect(box('window-0-morning').getAttribute('aria-label')).toBe('Monday, morning');
    expect(box('window-6-evening').getAttribute('aria-label')).toBe('Sunday, evening');
    expect(box('double-2').getAttribute('aria-label')).toBe('Wednesday, two sessions');
  });

  it('shows the values it is given', async () => {
    host.doubleDays.set([true, false, true, true, true, true, true]);
    host.timeWindows.set([['evening'], ...EVERY_DAY_OPEN.slice(1).map((day) => [...day])]);
    await settle(fixture);

    expect(box('double-1').checked).toBe(false);
    expect(box('double-0').checked).toBe(true);
    expect(box('window-0-morning').checked).toBe(false);
    expect(box('window-0-evening').checked).toBe(true);
    expect(box('window-1-morning').checked).toBe(true);
  });

  it('hands a change of two sessions to the page, day by day', async () => {
    await click('double-4');

    expect(host.doubleDays()).toEqual([true, true, true, true, false, true, true]);

    await click('double-4');

    expect(host.doubleDays()).toEqual(Array(7).fill(true));
  });

  it('hands a change of a part of the day to the page, in the order of the day', async () => {
    await click('window-2-afternoon');
    expect(host.timeWindows()[2]).toEqual(['morning', 'evening']);

    await click('window-2-morning');
    await click('window-2-afternoon');
    expect(host.timeWindows()[2]).toEqual(['afternoon', 'evening']);
    expect(host.timeWindows()[1]).toEqual(['morning', 'afternoon', 'evening']);
  });

  it('does not change the values it was given', async () => {
    const before = host.timeWindows();

    await click('window-0-morning');

    expect(before[0]).toEqual(['morning', 'afternoon', 'evening']);
    expect(host.timeWindows()).not.toBe(before);
  });

  it('shows a message under its weekday and marks that day’s boxes', async () => {
    host.errors.set([null, null, NO_WINDOW]);
    await settle(fixture);

    expect(query(element, '#window-2-error').textContent?.trim()).toBe(
      'Wednesday: Choose at least one part of the day.',
    );
    expect(box('window-2-morning').getAttribute('aria-invalid')).toBe('true');
    expect(box('window-2-morning').getAttribute('aria-describedby')).toBe('window-2-error');
    expect(box('window-1-morning').getAttribute('aria-invalid')).toBeNull();
    expect(element.querySelectorAll('[role="alert"]')).toHaveLength(1);
  });
});
