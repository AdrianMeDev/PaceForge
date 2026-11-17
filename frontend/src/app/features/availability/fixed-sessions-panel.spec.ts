import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  CreateFixedSessionResult,
  DeleteFixedSessionResult,
  FixedSession,
  FixedSessionInput,
  ListFixedSessionsResult,
} from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import { FixedSessionsPanel, sessionText } from './fixed-sessions-panel';

const CLUB: FixedSession = {
  id: 'club',
  weekday: 1,
  sport: 'running',
  minutes: 60,
  slot: 'evening',
};
const RIDE: FixedSession = { id: 'ride', weekday: 5, sport: 'cycling', minutes: 120, slot: null };

const ok = (...sessions: FixedSession[]): ListFixedSessionsResult => ({ kind: 'ok', sessions });

function createApiStub() {
  return {
    listFixedSessions: vi.fn<() => Promise<ListFixedSessionsResult>>(),
    createFixedSession: vi.fn<(input: FixedSessionInput) => Promise<CreateFixedSessionResult>>(),
    deleteFixedSession: vi.fn<(id: string) => Promise<DeleteFixedSessionResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('sessionText', () => {
  it('names the day, the sport, the minutes and the part of the day if there is one', () => {
    expect(sessionText(CLUB)).toBe('Tuesday · Running · 60 min · Evening');
    expect(sessionText(RIDE)).toBe('Saturday · Cycling · 120 min');
  });
});

describe('FixedSessionsPanel', () => {
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
  let fixture: ComponentFixture<FixedSessionsPanel>;
  let panel: HTMLElement;

  function create(first: ListFixedSessionsResult | Error) {
    api = createApiStub();
    if (first instanceof Error) {
      api.listFixedSessions.mockRejectedValueOnce(first);
      api.listFixedSessions.mockResolvedValue(ok(RIDE));
    } else {
      api.listFixedSessions.mockResolvedValue(first);
    }
    TestBed.configureTestingModule({
      imports: [FixedSessionsPanel],
      providers: [{ provide: AvailabilityApi, useValue: api }],
    });
    fixture = TestBed.createComponent(FixedSessionsPanel);
    panel = fixture.nativeElement as HTMLElement;
  }

  async function setup(first: ListFixedSessionsResult | Error = ok(CLUB, RIDE)) {
    create(first);
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const ids = () =>
    Array.from(panel.querySelectorAll('[data-testid^="fixed-"]')).map((e) =>
      e.getAttribute('data-testid')?.replace('fixed-', ''),
    );
  const notice = () => panel.querySelector('[role="status"]')?.textContent?.trim();

  async function click(target: Element | null | undefined): Promise<void> {
    (target as HTMLButtonElement).click();
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(panel, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  async function choose(id: string, value: string): Promise<void> {
    const select = query<HTMLSelectElement>(panel, `#${id}`);
    select.value = value;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      create(ok());
      api.listFixedSessions.mockReturnValue(new Promise<never>(() => undefined));
      fixture.detectChanges();

      expect(panel.querySelector('[role="status"][aria-label="Loading"]')).toBeTruthy();
    });

    it('says so and offers to try again when the list cannot be loaded', async () => {
      await setup(new Error('offline'));

      expect(alerts()).toEqual(['Your fixed appointments could not be loaded.']);

      await click(query(panel, 'button.btn-primary'));

      expect(ids()).toEqual(['ride']);
    });

    it('tells the page when the session is gone', async () => {
      create({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);
      await settle(fixture);

      expect(gone).toBe(1);
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup());

    it('says what is sent to the coach', () => {
      expect(panel.textContent).toContain('a day, a sport, the minutes and the part of the day');
    });

    it('lists the entries in the order sent, each in words', () => {
      expect(ids()).toEqual(['club', 'ride']);
      expect(query(panel, '[data-testid="fixed-club"] [data-testid="text"]').textContent).toBe(
        'Tuesday · Running · 60 min · Evening',
      );
    });

    it('says so when there is nothing yet', async () => {
      TestBed.resetTestingModule();
      await setup(ok());

      expect(panel.textContent).toContain('You have not entered anything yet.');
      expect(panel.querySelector('ul')).toBeNull();
    });
  });

  describe('adding', () => {
    beforeEach(() => setup(ok(RIDE)));

    it('offers the seven days, the sports and the parts of the day', () => {
      const values = (id: string) =>
        Array.from(panel.querySelectorAll<HTMLOptionElement>(`#${id} option`)).map((o) => o.value);

      expect(values('fixed-weekday')).toEqual(['0', '1', '2', '3', '4', '5', '6']);
      expect(values('fixed-sport')).toEqual(['running', 'cycling', 'swimming', 'strength']);
      expect(values('fixed-slot')).toEqual(['', 'morning', 'afternoon', 'evening']);
    });

    it('starts with Tuesday, running, 60 minutes and no part of the day', () => {
      expect(query<HTMLSelectElement>(panel, '#fixed-weekday').value).toBe('1');
      expect(query<HTMLSelectElement>(panel, '#fixed-sport').value).toBe('running');
      expect(query<HTMLInputElement>(panel, '#fixed-minutes').value).toBe('60');
      expect(query<HTMLSelectElement>(panel, '#fixed-slot').value).toBe('');
    });

    it('sends what was chosen, then shows the list and says so', async () => {
      api.createFixedSession.mockResolvedValue({ kind: 'ok', session: CLUB });
      api.listFixedSessions.mockResolvedValue(ok(CLUB, RIDE));
      await choose('fixed-weekday', '3');
      await choose('fixed-sport', 'swimming');
      await choose('fixed-slot', 'morning');
      typeInto(panel, '#fixed-minutes', ' 45 ');
      await settle(fixture);

      await submit();

      expect(api.createFixedSession).toHaveBeenCalledExactlyOnceWith({
        weekday: 3,
        sport: 'swimming',
        minutes: 45,
        slot: 'morning',
      });
      expect(ids()).toEqual(['club', 'ride']);
      expect(notice()).toBe('The entry was added.');
    });

    it('sends null when no part of the day is chosen', async () => {
      api.createFixedSession.mockResolvedValue({ kind: 'ok', session: RIDE });

      await submit();

      expect(api.createFixedSession).toHaveBeenCalledExactlyOnceWith({
        weekday: 1,
        sport: 'running',
        minutes: 60,
        slot: null,
      });
    });

    it.each(['', 'abc', '1.5', '-5', '6 0'])('does not send the minutes "%s"', async (text) => {
      typeInto(panel, '#fixed-minutes', text);
      await settle(fixture);

      await submit();

      expect(api.createFixedSession).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Enter a whole number of minutes between 5 and 600.']);
      expect(query(panel, '#fixed-minutes').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows the server’s messages next to their fields', async () => {
      api.createFixedSession.mockResolvedValue({
        kind: 'invalid',
        errors: ['Too long.', 'Unknown part.'],
        fields: { minutes: ['Too long.'], slot: ['Unknown part.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Too long.', 'Unknown part.']);
      expect(query(panel, '#fixed-slot').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message that no field owns above the form, once', async () => {
      const message = 'You can have at most 14 fixed appointments. Delete one first.';
      api.createFixedSession.mockResolvedValue({
        kind: 'invalid',
        errors: [message],
        fields: { non_field_errors: [message] },
      });

      await submit();

      expect(alerts()).toEqual([message]);
    });

    it('says something went wrong when the request fails', async () => {
      api.createFixedSession.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('tells the page when the session is gone', async () => {
      api.createFixedSession.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await submit();

      expect(gone).toBe(1);
    });

    it('does one thing at a time', async () => {
      const slow = deferred<CreateFixedSessionResult>();
      api.createFixedSession.mockReturnValue(slow.promise);

      void submit();
      await settle(fixture);
      await submit();

      expect(api.createFixedSession).toHaveBeenCalledTimes(1);
      slow.resolve({ kind: 'ok', session: CLUB });
      await settle(fixture);
    });
  });

  describe('deleting', () => {
    beforeEach(() => setup());

    const deleteButton = () =>
      query<HTMLButtonElement>(panel, 'button[aria-label^="Delete: Tuesday"]');

    it('asks first and does nothing when cancelled', async () => {
      await click(deleteButton());

      expect(query<HTMLDialogElement>(panel, '[data-testid="confirm-dialog"]').open).toBe(true);
      expect(
        query<HTMLDialogElement>(panel, '[data-testid="confirm-dialog"]').textContent,
      ).toContain('Delete this appointment: ');

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-cancel"]'));

      expect(query<HTMLDialogElement>(panel, '[data-testid="confirm-dialog"]').open).toBe(false);
      expect(api.deleteFixedSession).not.toHaveBeenCalled();
    });

    it('deletes after yes and fetches the list again', async () => {
      api.deleteFixedSession.mockResolvedValue({ kind: 'deleted' });
      api.listFixedSessions.mockResolvedValue(ok(RIDE));
      await click(deleteButton());

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]'));

      expect(api.deleteFixedSession).toHaveBeenCalledExactlyOnceWith('club');
      expect(ids()).toEqual(['ride']);
      expect(notice()).toBe('The entry was deleted.');
    });

    it('says when the entry was gone already', async () => {
      api.deleteFixedSession.mockResolvedValue({ kind: 'not_found' });
      api.listFixedSessions.mockResolvedValue(ok(RIDE));
      await click(deleteButton());

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]'));

      expect(notice()).toBe('That entry does not exist any more.');
    });

    it('tells the page when the session is gone', async () => {
      api.deleteFixedSession.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);
      await click(deleteButton());

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]'));

      expect(gone).toBe(1);
    });

    it('shows a failed refresh above the list', async () => {
      api.deleteFixedSession.mockResolvedValue({ kind: 'deleted' });
      api.listFixedSessions.mockRejectedValue(new Error('offline'));
      await click(deleteButton());

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]'));

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
    });

    it('says something went wrong when the request fails', async () => {
      api.deleteFixedSession.mockRejectedValue(new Error('offline'));
      await click(deleteButton());

      await click(query<HTMLButtonElement>(panel, '[data-testid="confirm-dialog-confirm"]'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });
  });
});
