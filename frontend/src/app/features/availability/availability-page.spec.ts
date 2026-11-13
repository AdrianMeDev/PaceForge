import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  Availability,
  AvailabilityChanges,
  GetAvailabilityResult,
  SaveAvailabilityResult,
} from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import { AvailabilityPage } from './availability-page';

const SAVED: Availability = {
  weekdays: [60, 0, 90, 0, 0, 120, 180],
  weekly_budget_minutes: 300,
  limitations: 'No running on consecutive days',
};
const NOTHING: Availability = {
  weekdays: [0, 0, 0, 0, 0, 0, 0],
  weekly_budget_minutes: null,
  limitations: '',
};

const ok = (availability: Availability): GetAvailabilityResult => ({ kind: 'ok', availability });

function createApiStub() {
  return {
    get: vi.fn<() => Promise<GetAvailabilityResult>>(),
    save: vi.fn<(changes: AvailabilityChanges) => Promise<SaveAvailabilityResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('AvailabilityPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<AvailabilityPage>;
  let page: HTMLElement;

  async function setup(first: GetAvailabilityResult = ok(SAVED)) {
    api = createApiStub();
    api.get.mockResolvedValue(first);
    api.save.mockResolvedValue({ kind: 'ok', availability: SAVED });
    TestBed.configureTestingModule({
      imports: [AvailabilityPage],
      providers: [provideRouter([]), { provide: AvailabilityApi, useValue: api }],
    });
    fixture = TestBed.createComponent(AvailabilityPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLTextAreaElement>(page, selector).value;
  const days = () => [0, 1, 2, 3, 4, 5, 6].map((i) => value(`#day-${i}`));
  const total = () => page.querySelector('[data-testid="total"]')?.textContent?.trim() ?? null;
  const capNote = () => page.querySelector('[data-testid="cap-note"]')?.textContent?.trim() ?? null;

  async function type(selector: string, input: string): Promise<void> {
    typeInto(page, selector, input);
    await settle(fixture);
  }

  async function save(): Promise<void> {
    query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      api = createApiStub();
      api.get.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [provideRouter([]), { provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when it cannot be loaded', async () => {
      api = createApiStub();
      api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(SAVED));
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [provideRouter([]), { provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your training time could not be loaded.']);

      query<HTMLButtonElement>(page, 'button.primary').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(days()[0]).toBe('1:00');
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('form')).toBeNull();
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup());

    it('has a labelled field for every weekday, Monday first', () => {
      const labels = Array.from(page.querySelectorAll('.days label')).map((l) =>
        l.textContent?.trim(),
      );

      expect(labels).toEqual([
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday',
        'Sunday',
      ]);
      for (const [i, label] of Array.from(page.querySelectorAll('.days label')).entries()) {
        expect(label.getAttribute('for')).toBe(`day-${i}`);
      }
    });

    it('shows the saved values as hours and minutes', () => {
      expect(days()).toEqual(['1:00', '0:00', '1:30', '0:00', '0:00', '2:00', '3:00']);
      expect(value('#budget')).toBe('5:00');
      expect(value('#limitations')).toBe('No running on consecutive days');
    });

    it('adds the days up', () => {
      expect(total()).toBe('Together: 7:30 per week');
    });

    it('says what the weekly budget does when it is below the sum', () => {
      expect(capNote()).toBe(
        'Your weekly budget (5:00) is lower than the sum of the days, so a week offers at most 5:00.',
      );
    });
  });

  describe('a user who saved nothing', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('sees zeros, no budget and no limitations', () => {
      expect(days()).toEqual(Array(7).fill('0:00'));
      expect(value('#budget')).toBe('');
      expect(value('#limitations')).toBe('');
      expect(total()).toBe('Together: 0:00 per week');
      expect(capNote()).toBeNull();
    });
  });

  describe('the sum while typing', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('follows every change', async () => {
      await type('#day-0', '90');
      expect(total()).toBe('Together: 1:30 per week');

      await type('#day-6', '1:00');
      expect(total()).toBe('Together: 2:30 per week');

      await type('#day-0', '');
      expect(total()).toBe('Together: 1:00 per week');
    });

    it('is not shown while a field is not a usable time', async () => {
      await type('#day-0', '60');
      await type('#day-1', 'abc');

      expect(total()).toBeNull();
    });

    it('comes back when the field is right again', async () => {
      await type('#day-1', 'abc');
      await type('#day-1', '30');

      expect(total()).toBe('Together: 0:30 per week');
    });

    it('says nothing about the budget when it is not below the sum', async () => {
      await type('#day-0', '60');
      await type('#budget', '1:00');
      expect(capNote()).toBeNull();

      await type('#budget', '2:00');
      expect(capNote()).toBeNull();
    });

    it('says it as soon as the budget is below the sum', async () => {
      await type('#day-0', '60');
      await type('#budget', '0:30');

      expect(capNote()).toContain('(0:30)');
    });

    it('says nothing for an empty or unusable budget', async () => {
      await type('#day-0', '60');
      await type('#budget', 'abc');
      expect(capNote()).toBeNull();

      await type('#budget', '');
      expect(capNote()).toBeNull();
    });

    it('says nothing while a day is unusable', async () => {
      await type('#budget', '0:30');
      await type('#day-0', '60');
      await type('#day-1', 'abc');

      expect(capNote()).toBeNull();
    });
  });

  describe('saving', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('sends the three together, minutes as numbers', async () => {
      await type('#day-0', '90');
      await type('#day-2', '1:30');
      await type('#day-6', '180');
      await type('#budget', '5:00');
      await type('#limitations', 'Knee');

      await save();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        weekdays: [90, 0, 90, 0, 0, 0, 180],
        weekly_budget_minutes: 300,
        limitations: 'Knee',
      });
    });

    it('sends no budget as null and empty days as zero', async () => {
      await type('#day-0', '');

      await save();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        weekdays: [0, 0, 0, 0, 0, 0, 0],
        weekly_budget_minutes: null,
        limitations: '',
      });
    });

    it('sends a budget of zero as zero', async () => {
      await type('#budget', '0');

      await save();

      expect(api.save.mock.calls[0][0].weekly_budget_minutes).toBe(0);
    });

    it('takes the limits themselves', async () => {
      for (let i = 0; i < 7; i++) {
        await type(`#day-${i}`, '24:00');
      }
      await type('#budget', '168:00');
      await type('#limitations', 'x'.repeat(1000));

      await save();

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(api.save.mock.calls[0][0].weekdays).toEqual(Array(7).fill(1440));
      expect(api.save.mock.calls[0][0].weekly_budget_minutes).toBe(10080);
    });

    it('shows what the server has now and says it was saved', async () => {
      api.save.mockResolvedValue({ kind: 'ok', availability: SAVED });
      await type('#day-0', '60');

      await save();

      expect(days()).toEqual(['1:00', '0:00', '1:30', '0:00', '0:00', '2:00', '3:00']);
      expect(value('#budget')).toBe('5:00');
      expect(text()).toContain('Your training time was saved.');
    });

    it('writes what was typed in the form of the answer', async () => {
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, weekdays: [90, 0, 0, 0, 0, 0, 0] },
      });
      await type('#day-0', '90');

      await save();

      expect(value('#day-0')).toBe('1:30');
    });

    it('clears the note with the next try', async () => {
      await save();
      expect(text()).toContain('Your training time was saved.');

      await type('#day-0', 'abc');
      await save();

      expect(text()).not.toContain('Your training time was saved.');
    });

    it('does not let the browser submit the page', async () => {
      const event = new Event('submit', { cancelable: true });
      query<HTMLFormElement>(page, 'form').dispatchEvent(event);
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
    });

    it('sends only once when submitted twice in a row, and shows that it is saving', async () => {
      const pending = deferred<SaveAvailabilityResult>();
      api.save.mockReturnValue(pending.promise);

      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await fixture.whenStable();
      fixture.detectChanges();
      const button = query<HTMLButtonElement>(page, 'button[type="submit"]');
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Saving');
      pending.resolve({ kind: 'ok', availability: NOTHING });
      await settle(fixture);

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(button.disabled).toBe(false);
    });
  });

  describe('input that cannot be used', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it.each(['abc', '1:5', '1:60', '-5', '1,5', '1441', '24:01'])(
      'refuses "%s" as a day, names the field and sends nothing',
      async (input) => {
        await type('#day-2', input);

        await save();

        expect(api.save).not.toHaveBeenCalled();
        expect(alerts()).toHaveLength(1);
        expect(query(page, '#day-2').getAttribute('aria-invalid')).toBe('true');
        expect(query(page, '#day-2').getAttribute('aria-describedby')).toBe('day-2-error');
        expect(query(page, '#day-2-error').textContent).toBeTruthy();
        expect(query(page, '#day-1').getAttribute('aria-invalid')).toBeNull();
      },
    );

    it('says what is expected and what the limit is', async () => {
      await type('#day-0', 'abc');
      await type('#day-1', '25:00');

      await save();

      expect(query(page, '#day-0-error').textContent?.trim()).toBe(
        'Enter minutes (90) or hours and minutes (1:30).',
      );
      expect(query(page, '#day-1-error').textContent?.trim()).toBe(
        'Enter at most 24:00 (1440 minutes).',
      );
    });

    it.each(['abc', '168:01', '10081'])('refuses "%s" as a budget', async (input) => {
      await type('#budget', input);

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toHaveLength(1);
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBe('true');
    });

    it('refuses limitations of more than 1000 characters', async () => {
      await type('#limitations', 'x'.repeat(1001));

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Use at most 1000 characters.']);
      expect(query(page, '#limitations').getAttribute('aria-invalid')).toBe('true');
    });

    it('names every problem at once', async () => {
      await type('#day-0', 'abc');
      await type('#day-6', 'xyz');
      await type('#budget', 'abc');
      await type('#limitations', 'x'.repeat(1001));

      await save();

      expect(alerts()).toHaveLength(4);
      expect(api.save).not.toHaveBeenCalled();
    });

    it('clears the messages once everything is right', async () => {
      await type('#day-0', 'abc');
      await type('#budget', 'abc');
      await save();
      expect(alerts()).toHaveLength(2);

      await type('#day-0', '60');
      await type('#budget', '');
      await save();

      expect(alerts()).toEqual([]);
      expect(api.save).toHaveBeenCalledTimes(1);
    });
  });

  describe('what the server says', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('shows a message about the weekdays above them', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter seven numbers of minutes, Monday first.'],
        fields: { weekdays: ['Enter seven numbers of minutes, Monday first.'] },
      });

      await save();

      expect(alerts()).toEqual(['Enter seven numbers of minutes, Monday first.']);
      expect(query(page, '.panel > .field-error').textContent).toContain('seven numbers');
    });

    it('shows a message about the budget next to it', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter whole minutes between 0 and 10080.'],
        fields: { weekly_budget_minutes: ['Enter whole minutes between 0 and 10080.'] },
      });

      await save();

      expect(alerts()).toEqual(['Enter whole minutes between 0 and 10080.']);
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message about the limitations next to them', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Not a valid string.'],
        fields: { limitations: ['Not a valid string.'] },
      });

      await save();

      expect(alerts()).toEqual(['Not a valid string.']);
      expect(query(page, '#limitations').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message about anything else at the top, once', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Something odd.'],
        fields: { non_field_errors: ['Something odd.'] },
      });

      await save();

      expect(alerts()).toEqual(['Something odd.']);
      expect(query(page, 'form').previousElementSibling?.textContent).toContain('Something odd.');
    });

    it('shows a refusal without fields as it is', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });

      await save();

      expect(alerts()).toEqual(['The input was not accepted.']);
    });

    it('joins several messages for one field', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['First.', 'Second.'],
        fields: { weekly_budget_minutes: ['First.', 'Second.'] },
      });

      await save();

      expect(alerts()).toEqual(['First. Second.']);
    });

    it('clears an earlier message at the top once a save works', async () => {
      api.save.mockResolvedValueOnce({
        kind: 'invalid',
        errors: ['Something odd.'],
        fields: { non_field_errors: ['Something odd.'] },
      });
      await save();
      expect(alerts()).toEqual(['Something odd.']);

      await save();

      expect(alerts()).toEqual([]);
    });

    it('keeps what the user typed', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['No.'],
        fields: { weekdays: ['No.'] },
      });
      await type('#day-3', '45');

      await save();

      expect(value('#day-3')).toBe('45');
    });

    it('says that the session has ended', async () => {
      api.save.mockResolvedValue({ kind: 'forbidden' });

      await save();

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when saving does not work', async () => {
      api.save.mockRejectedValue(new Error('offline'));

      await save();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(page.querySelector('form')).not.toBeNull();
    });
  });

  describe('free text', () => {
    it('shows the limitations as text and never as markup', async () => {
      await setup(ok({ ...NOTHING, limitations: '<img src=x onerror=alert(1)><b>bold</b>' }));

      expect(value('#limitations')).toBe('<img src=x onerror=alert(1)><b>bold</b>');
      expect(page.querySelector('img')).toBeNull();
      expect(page.querySelector('b')).toBeNull();
    });
  });
});
