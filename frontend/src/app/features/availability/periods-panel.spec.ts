import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  CreatePeriodResult,
  DeletePeriodResult,
  ListPeriodsResult,
  Period,
  PeriodInput,
} from '../../core/availability/availability-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { PeriodsPanel } from './periods-panel';

const GOING_ON: Period = {
  id: 'on',
  kind: 'illness',
  start_date: '2026-11-12',
  end_date: '2026-11-15',
  days: 4,
  status: 'current',
  note: '',
};
const COMING: Period = {
  id: 'coming',
  kind: 'vacation',
  start_date: '2026-11-23',
  end_date: '2026-12-06',
  days: 14,
  status: 'upcoming',
  note: 'Mallorca <b>x</b>',
};
const ONE_DAY: Period = {
  id: 'one',
  kind: 'other',
  start_date: '2026-11-20',
  end_date: '2026-11-20',
  days: 1,
  status: 'upcoming',
  note: '',
};
const OVER: Period = {
  id: 'over',
  kind: 'other',
  start_date: '2026-10-14',
  end_date: '2026-10-24',
  days: 11,
  status: 'past',
  note: '',
};

const ok = (...periods: Period[]): ListPeriodsResult => ({ kind: 'ok', periods });

function createApiStub() {
  return {
    listPeriods: vi.fn<() => Promise<ListPeriodsResult>>(),
    createPeriod: vi.fn<(input: PeriodInput) => Promise<CreatePeriodResult>>(),
    deletePeriod: vi.fn<(id: string) => Promise<DeletePeriodResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('PeriodsPanel', () => {
  // jsdom has no modal dialog: this is what the browser does that the question relies on.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open');
        this.dispatchEvent(new Event('close'));
      }
    };
  });

  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<PeriodsPanel>;
  let panel: HTMLElement;

  const dialog = () => query<HTMLDialogElement>(panel, '[data-testid="confirm-dialog"]');
  const confirmButton = () =>
    query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]');
  const cancelButton = () =>
    query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-cancel"]');
  // the buttons of the dialog are not the panel's: the dialog is closed
  const pageButtons = () =>
    Array.from(panel.querySelectorAll<HTMLButtonElement>('button:not(app-confirm-dialog button)'));
  let events: string[];

  async function setup(first: ListPeriodsResult = ok(GOING_ON, COMING, OVER)) {
    api = createApiStub();
    api.listPeriods.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [PeriodsPanel],
      providers: [{ provide: AvailabilityApi, useValue: api }],
    });
    fixture = TestBed.createComponent(PeriodsPanel);
    events = [];
    fixture.componentInstance.signedOut.subscribe(() => events.push('signedOut'));
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => panel.textContent ?? '';
  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const ids = () =>
    Array.from(panel.querySelectorAll('.period')).map((e) =>
      e.getAttribute('data-testid')?.replace('period-', ''),
    );
  const card = (id: string) => query(panel, `[data-testid="period-${id}"]`);
  const within = (id: string, testId: string) =>
    card(id).querySelector(`[data-testid="${testId}"]`)?.textContent?.replace(/\s+/g, ' ').trim();

  function buttonWithText(label: string): HTMLButtonElement {
    const match = Array.from(panel.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  function labelled(label: string): HTMLButtonElement {
    return required(
      panel.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`),
      `a button "${label}"`,
    );
  }

  async function click(target: HTMLButtonElement): Promise<void> {
    target.click();
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the list arrives', () => {
      api = createApiStub();
      api.listPeriods.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [PeriodsPanel],
        providers: [{ provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(PeriodsPanel);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
      expect(fixture.nativeElement.querySelector('.period')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.listPeriods).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the list cannot be loaded', async () => {
      api = createApiStub();
      api.listPeriods.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(COMING));
      TestBed.configureTestingModule({
        imports: [PeriodsPanel],
        providers: [{ provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(PeriodsPanel);
      panel = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your periods could not be loaded.']);

      await click(buttonWithText('Try again'));

      expect(alerts()).toEqual([]);
      expect(ids()).toEqual(['coming']);
    });

    it('tells the page when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(events).toEqual(['signedOut']);
      expect(panel.querySelector('.period')).toBeNull();
    });

    it('shows an empty state and still offers to add a period', async () => {
      await setup(ok());

      expect(text()).toContain('You have not entered any period yet.');
      expect(buttonWithText('Add period')).toBeTruthy();
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup(ok(GOING_ON, COMING, ONE_DAY, OVER)));

    it('keeps the order the server sent', () => {
      expect(ids()).toEqual(['on', 'coming', 'one', 'over']);
    });

    it('names the kind', () => {
      expect(card('on').textContent).toContain('Illness');
      expect(card('coming').textContent).toContain('Vacation');
      expect(card('one').textContent).toContain('Other');
    });

    it('shows both dates and the length of a period of several days', () => {
      expect(within('coming', 'dates')).toBe('Nov 23, 2026 – Dec 6, 2026 (14 days)');
      expect(within('on', 'dates')).toBe('Nov 12, 2026 – Nov 15, 2026 (4 days)');
    });

    it('shows one date for a single day', () => {
      expect(within('one', 'dates')).toBe('Nov 20, 2026 (1 day)');
    });

    it('marks the period that is going on and the ones that are over', () => {
      expect(card('on').textContent).toContain('Now');
      expect(card('coming').textContent).not.toContain('Now');
      expect(card('over').textContent).toContain('Past');
      expect(card('coming').textContent).not.toContain('Past');
      expect(card('one').textContent).not.toContain('Past');
    });

    it('shows the note as text and never as markup', () => {
      expect(within('coming', 'note')).toBe('Mallorca <b>x</b>');
      expect(panel.querySelector('.note b')).toBeNull();
      expect(card('on').querySelector('[data-testid="note"]')).toBeNull();
    });

    it('names the period in the delete button for assistive technology', () => {
      expect(labelled('Delete vacation from 2026-11-23')).toBeTruthy();
      expect(labelled('Delete illness from 2026-11-12')).toBeTruthy();
    });
  });

  describe('adding', () => {
    const CREATED: Period = { ...COMING, id: 'new', note: '' };

    beforeEach(() => setup(ok(COMING)));

    it('opens the form and hides the button for it', async () => {
      await click(buttonWithText('Add period'));

      expect(panel.querySelector('form')).not.toBeNull();
      expect(query(panel, 'h3').textContent).toBe('Add a period');
      expect(panel.querySelector('p > button.btn-primary')).toBeNull();
    });

    it('closes the form again with Cancel and sends nothing', async () => {
      await click(buttonWithText('Add period'));

      await click(buttonWithText('Cancel'));

      expect(panel.querySelector('form')).toBeNull();
      expect(api.createPeriod).not.toHaveBeenCalled();
      expect(buttonWithText('Add period')).toBeTruthy();
    });

    it('saves a period, closes the form, says so and fetches the list again', async () => {
      api.createPeriod.mockResolvedValue({ kind: 'ok', period: CREATED });
      api.listPeriods.mockResolvedValue(ok(COMING, CREATED));
      await click(buttonWithText('Add period'));
      typeInto(panel, '#period-start', '2026-11-23');
      typeInto(panel, '#period-end', '2026-12-06');
      await settle(fixture);

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(api.createPeriod).toHaveBeenCalledTimes(1);
      expect(panel.querySelector('form')).toBeNull();
      expect(text()).toContain('The period was added.');
      expect(api.listPeriods).toHaveBeenCalledTimes(2);
      expect(ids()).toEqual(['coming', 'new']);
    });

    it('keeps the form and its entries when the server refuses', async () => {
      api.createPeriod.mockResolvedValue({
        kind: 'invalid',
        errors: ['No.'],
        fields: { end_date: ['No.'] },
      });
      await click(buttonWithText('Add period'));
      typeInto(panel, '#period-start', '2026-11-23');
      await settle(fixture);

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(panel.querySelector('form')).not.toBeNull();
      expect(query<HTMLInputElement>(panel, '#period-start').value).toBe('2026-11-23');
      expect(alerts()).toEqual(['No.']);
      expect(api.listPeriods).toHaveBeenCalledTimes(1);
    });

    it('tells the page when the session ended while saving', async () => {
      api.createPeriod.mockResolvedValue({ kind: 'forbidden' });
      await click(buttonWithText('Add period'));
      typeInto(panel, '#period-start', '2026-11-23');
      await settle(fixture);

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(events).toEqual(['signedOut']);
    });

    it('clears an earlier message when the form opens', async () => {
      api.deletePeriod.mockRejectedValue(new Error('offline'));
      await click(labelled('Delete vacation from 2026-11-23'));
      await click(confirmButton());
      expect(alerts()).toEqual(['Something went wrong. Please try again.']);

      await click(buttonWithText('Add period'));

      expect(alerts()).toEqual([]);
    });
  });

  describe('deleting', () => {
    beforeEach(() => setup(ok(GOING_ON, COMING)));

    it('asks first and deletes nothing until confirmed', async () => {
      await click(labelled('Delete vacation from 2026-11-23'));

      expect(dialog().open).toBe(true);
      expect(dialog().textContent).toContain('Delete the vacation from');
      expect(api.deletePeriod).not.toHaveBeenCalled();
    });

    it('does nothing when cancelled', async () => {
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(cancelButton());

      expect(api.deletePeriod).not.toHaveBeenCalled();
      expect(dialog().open).toBe(false);
      expect(api.listPeriods).toHaveBeenCalledTimes(1);
    });

    it('asks about one period at a time', async () => {
      await click(labelled('Delete vacation from 2026-11-23'));
      await click(labelled('Delete illness from 2026-11-12'));

      expect(panel.querySelectorAll('[data-testid="confirm-dialog"]')).toHaveLength(1);
      expect(dialog().textContent).toContain('Delete the illness from');
    });

    it('deletes the confirmed period, says so and fetches the list again', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'deleted' });
      api.listPeriods.mockResolvedValue(ok(GOING_ON));
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(api.deletePeriod).toHaveBeenCalledExactlyOnceWith('coming');
      expect(ids()).toEqual(['on']);
      expect(text()).toContain('The period was deleted.');
    });

    it('treats a period that is already gone as deleted, and says so', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'not_found' });
      api.listPeriods.mockResolvedValue(ok(GOING_ON));
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(text()).toContain('That period does not exist any more.');
      expect(ids()).toEqual(['on']);
    });

    it('shows the empty state after the last period is deleted', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'deleted' });
      api.listPeriods.mockResolvedValue(ok());
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(text()).toContain('You have not entered any period yet.');
    });

    it('tells the page when the session ended', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'forbidden' });
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(events).toEqual(['signedOut']);
    });

    it('says so when deleting does not work and keeps the period', async () => {
      api.deletePeriod.mockRejectedValue(new Error('offline'));
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(ids()).toEqual(['on', 'coming']);
    });

    it('keeps the old list and says so when the refresh fails', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'deleted' });
      api.listPeriods.mockRejectedValue(new Error('offline'));
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
      expect(ids()).toEqual(['on', 'coming']);
      expect(text()).toContain('The period was deleted.');
      expect(dialog().open).toBe(false);
    });

    it('tells the page when the refresh finds the session gone', async () => {
      api.deletePeriod.mockResolvedValue({ kind: 'deleted' });
      api.listPeriods.mockResolvedValue({ kind: 'forbidden' });
      await click(labelled('Delete vacation from 2026-11-23'));

      await click(confirmButton());

      expect(events).toEqual(['signedOut']);
    });

    it('deletes only once when confirmed twice in a row', async () => {
      const pending = deferred<DeletePeriodResult>();
      api.deletePeriod.mockReturnValue(pending.promise);
      await click(labelled('Delete vacation from 2026-11-23'));

      const confirm = confirmButton();
      confirm.click();
      confirm.click();
      pending.resolve({ kind: 'deleted' });
      await settle(fixture);

      expect(api.deletePeriod).toHaveBeenCalledTimes(1);
    });

    it('disables the buttons while a deletion runs', async () => {
      const pending = deferred<DeletePeriodResult>();
      api.deletePeriod.mockReturnValue(pending.promise);
      await click(labelled('Delete vacation from 2026-11-23'));

      confirmButton().click();
      fixture.detectChanges();

      expect(pageButtons().every((b) => b.disabled)).toBe(true);
      pending.resolve({ kind: 'deleted' });
      await settle(fixture);
      expect(pageButtons().some((b) => b.disabled)).toBe(false);
    });

    it('clears an earlier message when it asks', async () => {
      api.deletePeriod.mockRejectedValue(new Error('offline'));
      await click(labelled('Delete vacation from 2026-11-23'));
      await click(confirmButton());
      expect(alerts()).toHaveLength(1);

      await click(labelled('Delete illness from 2026-11-12'));

      expect(alerts()).toEqual([]);
    });
  });
});
