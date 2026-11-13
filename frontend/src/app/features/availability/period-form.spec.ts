import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  CreatePeriodResult,
  Period,
  PeriodInput,
} from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import { PeriodForm } from './period-form';

const CREATED: Period = {
  id: 'p1',
  kind: 'vacation',
  start_date: '2026-11-23',
  end_date: '2026-12-06',
  days: 14,
  status: 'upcoming',
  note: '',
};

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('PeriodForm', () => {
  let api: {
    createPeriod: ReturnType<typeof vi.fn<(input: PeriodInput) => Promise<CreatePeriodResult>>>;
  };
  let fixture: ComponentFixture<PeriodForm>;
  let form: HTMLElement;
  let saved: Period[];
  let events: string[];

  async function setup() {
    api = { createPeriod: vi.fn() };
    api.createPeriod.mockResolvedValue({ kind: 'ok', period: CREATED });
    TestBed.configureTestingModule({
      imports: [PeriodForm],
      providers: [{ provide: AvailabilityApi, useValue: api }],
    });
    fixture = TestBed.createComponent(PeriodForm);
    saved = [];
    events = [];
    fixture.componentInstance.saved.subscribe((p) => saved.push(p));
    fixture.componentInstance.cancelled.subscribe(() => events.push('cancelled'));
    fixture.componentInstance.signedOut.subscribe(() => events.push('signedOut'));
    form = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  async function type(selector: string, value: string): Promise<void> {
    typeInto(form, selector, value);
    await settle(fixture);
  }

  async function choose(value: string): Promise<void> {
    const select = query<HTMLSelectElement>(form, '#period-kind');
    select.value = value;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(form.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLSelectElement>(form, selector).value;

  beforeEach(() => setup());

  describe('opening', () => {
    it('is headed "Add a period", offers the kinds and starts empty', () => {
      expect(query(form, 'h3').textContent).toBe('Add a period');
      expect(
        Array.from(form.querySelectorAll('#period-kind option')).map((o) => o.textContent?.trim()),
      ).toEqual(['Vacation', 'Illness', 'Other']);
      expect(value('#period-kind')).toBe('vacation');
      expect(value('#period-start')).toBe('');
      expect(value('#period-end')).toBe('');
      expect(value('#period-note')).toBe('');
    });

    it('puts the cursor in the first day', async () => {
      TestBed.resetTestingModule();
      await setup();
      try {
        fixture.destroy();
        fixture = TestBed.createComponent(PeriodForm);
        document.body.appendChild(fixture.nativeElement);
        fixture.detectChanges();
        await settle(fixture);

        expect(document.activeElement?.id).toBe('period-start');
      } finally {
        document.body.replaceChildren();
      }
    });
  });

  describe('the last day', () => {
    it('follows the first day while it is empty', async () => {
      await type('#period-start', '2026-11-23');

      expect(value('#period-end')).toBe('2026-11-23');
    });

    it('is left alone once it has a value', async () => {
      await type('#period-end', '2026-12-06');

      await type('#period-start', '2026-11-23');

      expect(value('#period-end')).toBe('2026-12-06');
    });

    it('is not overwritten when the first day changes again', async () => {
      await type('#period-start', '2026-11-23');
      await type('#period-end', '2026-12-06');

      await type('#period-start', '2026-11-20');

      expect(value('#period-end')).toBe('2026-12-06');
    });
  });

  describe('saving', () => {
    it('sends a vacation as it is typed', async () => {
      await type('#period-start', '2026-11-23');
      await type('#period-end', '2026-12-06');
      await type('#period-note', 'Mallorca');

      await submit();

      expect(api.createPeriod).toHaveBeenCalledExactlyOnceWith({
        kind: 'vacation',
        start_date: '2026-11-23',
        end_date: '2026-12-06',
        note: 'Mallorca',
      });
      expect(saved).toEqual([CREATED]);
    });

    it('sends the chosen kind', async () => {
      await choose('illness');
      await type('#period-start', '2026-11-12');

      await submit();

      expect(api.createPeriod.mock.calls[0][0]).toMatchObject({ kind: 'illness' });
    });

    it('sends one day when only the first day is entered', async () => {
      await type('#period-start', '2026-11-12');

      await submit();

      expect(api.createPeriod).toHaveBeenCalledExactlyOnceWith({
        kind: 'vacation',
        start_date: '2026-11-12',
        end_date: '2026-11-12',
        note: '',
      });
    });

    it('takes 366 days and a note of 200 characters', async () => {
      await type('#period-start', '2027-01-01');
      await type('#period-end', '2028-01-01');
      await type('#period-note', 'x'.repeat(200));

      await submit();

      expect(api.createPeriod).toHaveBeenCalledTimes(1);
    });

    it('does not let the browser submit the page', async () => {
      const event = new Event('submit', { cancelable: true });
      query<HTMLFormElement>(form, 'form').dispatchEvent(event);
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
    });

    it('sends only once when submitted twice in a row, and shows that it is saving', async () => {
      await type('#period-start', '2026-11-12');
      const pending = deferred<CreatePeriodResult>();
      api.createPeriod.mockReturnValue(pending.promise);

      query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await fixture.whenStable();
      fixture.detectChanges();
      const button = query<HTMLButtonElement>(form, 'button[type="submit"]');
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Saving');
      pending.resolve({ kind: 'ok', period: CREATED });
      await settle(fixture);

      expect(api.createPeriod).toHaveBeenCalledTimes(1);
      expect(button.disabled).toBe(false);
    });

    it('cancels without sending anything', () => {
      query<HTMLButtonElement>(form, 'button.link').click();

      expect(events).toEqual(['cancelled']);
      expect(api.createPeriod).not.toHaveBeenCalled();
    });
  });

  describe('input that cannot be used', () => {
    it('asks for both days and names the fields', async () => {
      await submit();

      expect(alerts()).toEqual(['Enter the first day.', 'Enter the last day.']);
      expect(query(form, '#period-start').getAttribute('aria-invalid')).toBe('true');
      expect(query(form, '#period-start').getAttribute('aria-describedby')).toBe(
        'period-start-error',
      );
      expect(query(form, '#period-end').getAttribute('aria-describedby')).toBe('period-end-error');
      expect(api.createPeriod).not.toHaveBeenCalled();
    });

    it('asks for the last day when it was emptied', async () => {
      await type('#period-start', '2026-11-12');
      await type('#period-end', '');

      await submit();

      expect(alerts()).toEqual(['Enter the last day.']);
    });

    it('refuses an end before the start', async () => {
      await type('#period-start', '2026-11-12');
      await type('#period-end', '2026-11-11');

      await submit();

      expect(alerts()).toEqual(['The end cannot be before the start.']);
      expect(query(form, '#period-end').getAttribute('aria-invalid')).toBe('true');
      expect(query(form, '#period-start').getAttribute('aria-invalid')).toBeNull();
    });

    it('refuses more than 366 days', async () => {
      await type('#period-start', '2027-01-01');
      await type('#period-end', '2028-01-02');

      await submit();

      expect(alerts()).toEqual(['A period can last at most 366 days.']);
      expect(api.createPeriod).not.toHaveBeenCalled();
    });

    it.each(['#period-start', '#period-end'])(
      'refuses text that is no date in %s',
      async (selector) => {
        // a browser's date field never gives this, but the form does not rely on it
        for (const id of ['#period-start', '#period-end']) {
          query<HTMLInputElement>(form, id).type = 'text';
        }
        await type('#period-start', '2026-11-12');
        await type('#period-end', '2026-11-13');
        await type(selector, 'soon');

        await submit();

        expect(alerts()).toEqual(['Enter a date like 2027-07-12.']);
        expect(query(form, selector).getAttribute('aria-invalid')).toBe('true');
      },
    );

    it('refuses a date that does not exist', async () => {
      for (const id of ['#period-start', '#period-end']) {
        query<HTMLInputElement>(form, id).type = 'text';
      }
      await type('#period-start', '2027-02-30');
      await type('#period-end', '2027-03-02');

      await submit();

      expect(alerts()).toEqual(['Enter a date like 2027-07-12.']);
    });

    it('refuses a note of more than 200 characters', async () => {
      await type('#period-start', '2026-11-12');
      await type('#period-note', 'x'.repeat(201));

      await submit();

      expect(alerts()).toEqual(['Use at most 200 characters.']);
      expect(query(form, '#period-note').getAttribute('aria-invalid')).toBe('true');
    });

    it('names every problem at once', async () => {
      await type('#period-note', 'x'.repeat(201));

      await submit();

      expect(alerts()).toHaveLength(3);
    });

    it('clears the messages once everything is right', async () => {
      await submit();
      expect(alerts()).toHaveLength(2);

      await type('#period-start', '2026-11-12');
      await submit();

      expect(alerts()).toEqual([]);
      expect(api.createPeriod).toHaveBeenCalledTimes(1);
    });
  });

  describe('what the server says', () => {
    beforeEach(() => type('#period-start', '2026-11-12'));

    it.each([
      ['kind', '#period-kind'],
      ['start_date', '#period-start'],
      ['end_date', '#period-end'],
      ['note', '#period-note'],
    ])('places a message for "%s" at its field', async (field, selector) => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['Nope.'],
        fields: { [field]: ['Nope.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Nope.']);
      const next = query(form, selector).parentElement?.querySelector('.field-error');
      expect(next?.textContent).toBe('Nope.');
    });

    it('shows a problem of the whole period at the top of the form', async () => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['You can have at most 100 periods. Delete one first.'],
        fields: { non_field_errors: ['You can have at most 100 periods. Delete one first.'] },
      });

      await submit();

      expect(alerts()).toEqual(['You can have at most 100 periods. Delete one first.']);
      expect(query(form, 'form > .alert').textContent).toContain('100 periods');
    });

    it('shows a refusal without fields as it is', async () => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });

      await submit();

      expect(alerts()).toEqual(['The input was not accepted.']);
    });

    it('joins several messages for one field and collects unknown fields in one place', async () => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['A.', 'B.', 'C.', 'D.'],
        fields: { note: ['A.', 'B.'], non_field_errors: ['C.'], other: ['D.'] },
      });

      await submit();

      expect(alerts()).toEqual(['C. D.', 'A. B.']);
    });

    it('keeps what the user typed', async () => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['No.'],
        fields: { end_date: ['No.'] },
      });
      await type('#period-note', 'Mallorca');

      await submit();

      expect(value('#period-start')).toBe('2026-11-12');
      expect(value('#period-note')).toBe('Mallorca');
    });

    it('clears the messages with the next try', async () => {
      api.createPeriod.mockResolvedValueOnce({ kind: 'invalid', errors: ['No.'], fields: {} });
      await submit();
      expect(alerts()).toEqual(['No.']);

      await submit();

      expect(alerts()).toEqual([]);
      expect(saved).toEqual([CREATED]);
    });

    it('reports a gone session', async () => {
      api.createPeriod.mockResolvedValue({ kind: 'forbidden' });

      await submit();

      expect(events).toEqual(['signedOut']);
      expect(saved).toEqual([]);
    });

    it('says so when saving does not work', async () => {
      api.createPeriod.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(saved).toEqual([]);
    });
  });
});
