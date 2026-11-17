import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  CreateLimitationResult,
  DeleteLimitationResult,
  Limitation,
  LimitationChanges,
  LimitationInput,
  ListLimitationsResult,
  UpdateLimitationResult,
} from '../../core/availability/availability-models';
import { query, settle } from '../../testing/dom';
import { LimitationsPanel, sportsText } from './limitations-panel';

const ACHILLES: Limitation = {
  id: 'achilles',
  body_part: 'achilles',
  status: 'current',
  sports: ['running', 'cycling'],
};
const BACK: Limitation = { id: 'back', body_part: 'back', status: 'current', sports: [] };
const KNEE: Limitation = { id: 'knee', body_part: 'knee', status: 'healed', sports: ['running'] };

const ok = (...limitations: Limitation[]): ListLimitationsResult => ({
  kind: 'ok',
  limitations,
});

function createApiStub() {
  return {
    listLimitations: vi.fn<() => Promise<ListLimitationsResult>>(),
    createLimitation: vi.fn<(input: LimitationInput) => Promise<CreateLimitationResult>>(),
    updateLimitation:
      vi.fn<(id: string, changes: LimitationChanges) => Promise<UpdateLimitationResult>>(),
    deleteLimitation: vi.fn<(id: string) => Promise<DeleteLimitationResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('sportsText', () => {
  it('names the sports in the order of the sports, or says none in particular', () => {
    expect(sportsText([])).toBe('No particular sport');
    expect(sportsText(['strength', 'running'])).toBe('Running, Strength / gym');
  });
});

describe('LimitationsPanel', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<LimitationsPanel>;
  let panel: HTMLElement;

  async function setup(first: ListLimitationsResult = ok(ACHILLES, BACK, KNEE)) {
    api = createApiStub();
    api.listLimitations.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [LimitationsPanel],
      providers: [{ provide: AvailabilityApi, useValue: api }],
    });
    fixture = TestBed.createComponent(LimitationsPanel);
    fixture.componentRef.setInput('provider', 'Anthropic, model claude-sonnet-5-5');
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const ids = () =>
    Array.from(panel.querySelectorAll('[data-testid^="limitation-"]')).map((e) =>
      e.getAttribute('data-testid')?.replace('limitation-', ''),
    );
  const card = (id: string) => query(panel, `[data-testid="limitation-${id}"]`);
  const within = (id: string, testId: string) =>
    query(card(id), `[data-testid="${testId}"]`).textContent?.trim();

  function labelled(label: string): HTMLButtonElement {
    return query<HTMLButtonElement>(panel, `button[aria-label="${label}"]`);
  }

  async function click(target: HTMLButtonElement): Promise<void> {
    target.click();
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(panel, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  async function choose(part: string): Promise<void> {
    const select = query<HTMLSelectElement>(panel, '#limitation-body-part');
    select.value = part;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function tick(sport: string): Promise<void> {
    query<HTMLInputElement>(panel, `#limitation-sport-${sport}`).click();
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      api = createApiStub();
      api.listLimitations.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [LimitationsPanel],
        providers: [{ provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(LimitationsPanel);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
    });

    it('says so and offers to try again when the list cannot be loaded', async () => {
      api = createApiStub();
      api.listLimitations.mockRejectedValueOnce(new Error('offline'));
      api.listLimitations.mockResolvedValue(ok(BACK));
      TestBed.configureTestingModule({
        imports: [LimitationsPanel],
        providers: [{ provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(LimitationsPanel);
      panel = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your limitations could not be loaded.']);

      query<HTMLButtonElement>(panel, 'button.btn-primary').click();
      await settle(fixture);

      expect(ids()).toEqual(['back']);
    });

    it('tells the page when the session is gone', async () => {
      api = createApiStub();
      api.listLimitations.mockResolvedValue({ kind: 'forbidden' });
      TestBed.configureTestingModule({
        imports: [LimitationsPanel],
        providers: [{ provide: AvailabilityApi, useValue: api }],
      });
      fixture = TestBed.createComponent(LimitationsPanel);
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);
      await settle(fixture);

      expect(gone).toBe(1);
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup());

    it('names the provider the entries go to and says what is sent', () => {
      const text = panel.textContent ?? '';

      expect(text).toContain('Where they go: Anthropic, model claude-sonnet-5-5.');
      expect(text).toContain('as a body part and the sports it affects, without any text of yours');
      expect(text).toContain('Healed entries stay here as a record and are not sent.');
    });

    it('lists the entries in the order sent', () => {
      expect(ids()).toEqual(['achilles', 'back', 'knee']);
    });

    it('shows the body part, the status and the sports of each', () => {
      expect(within('achilles', 'part')).toBe('Achilles tendon');
      expect(within('achilles', 'status')).toBe('Current');
      expect(within('achilles', 'sports')).toBe('Running, Cycling');
      expect(within('back', 'sports')).toBe('No particular sport');
      expect(within('knee', 'status')).toBe('Healed');
      expect(card('knee').getAttribute('data-status')).toBe('healed');
    });

    it('says so when there is nothing yet', async () => {
      TestBed.resetTestingModule();
      await setup(ok());

      expect(panel.textContent).toContain('You have not entered anything yet.');
      expect(panel.querySelector('ul')).toBeNull();
    });
  });

  describe('adding', () => {
    beforeEach(() => setup(ok(BACK)));

    it('offers every body part, the knee first chosen', () => {
      const options = Array.from(
        panel.querySelectorAll<HTMLOptionElement>('#limitation-body-part option'),
      );

      expect(options.map((o) => o.value)).toEqual([
        'foot',
        'ankle',
        'achilles',
        'calf',
        'shin',
        'knee',
        'thigh',
        'hip',
        'back',
        'shoulder',
        'other',
      ]);
      expect(query<HTMLSelectElement>(panel, '#limitation-body-part').value).toBe('knee');
    });

    it('sends the body part and the sports in the order of the sports, then shows the list', async () => {
      api.createLimitation.mockResolvedValue({ kind: 'ok', limitation: ACHILLES });
      api.listLimitations.mockResolvedValue(ok(ACHILLES, BACK));
      await choose('achilles');
      await tick('cycling');
      await tick('running');

      await submit();

      expect(api.createLimitation).toHaveBeenCalledExactlyOnceWith({
        body_part: 'achilles',
        sports: ['running', 'cycling'],
      });
      expect(ids()).toEqual(['achilles', 'back']);
      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe(
        'The entry was added.',
      );
    });

    it('sends no sports when none is ticked', async () => {
      api.createLimitation.mockResolvedValue({ kind: 'ok', limitation: KNEE });

      await submit();

      expect(api.createLimitation).toHaveBeenCalledExactlyOnceWith({
        body_part: 'knee',
        sports: [],
      });
    });

    it('clears the ticked sports after an entry was added', async () => {
      api.createLimitation.mockResolvedValue({ kind: 'ok', limitation: KNEE });
      await tick('running');

      await submit();

      expect(query<HTMLInputElement>(panel, '#limitation-sport-running').checked).toBe(false);
    });

    it('shows the server’s messages next to their fields', async () => {
      api.createLimitation.mockResolvedValue({
        kind: 'invalid',
        errors: ['Choose one of: foot.', 'Choose any of: running.'],
        fields: { body_part: ['Choose one of: foot.'], sports: ['Choose any of: running.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Choose one of: foot.', 'Choose any of: running.']);
      expect(query(panel, '#limitation-body-part').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message that no field owns above the form, once', async () => {
      const message = 'You can have at most 50 limitations. Delete one first.';
      api.createLimitation.mockResolvedValue({
        kind: 'invalid',
        errors: [message],
        fields: { non_field_errors: [message] },
      });

      await submit();

      expect(alerts()).toEqual([message]);
    });

    it('says something went wrong when the request fails', async () => {
      api.createLimitation.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('tells the page when the session is gone', async () => {
      api.createLimitation.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await submit();

      expect(gone).toBe(1);
    });

    it('does one thing at a time', async () => {
      const slow = deferred<CreateLimitationResult>();
      api.createLimitation.mockReturnValue(slow.promise);

      void submit();
      await settle(fixture);
      await submit();

      expect(api.createLimitation).toHaveBeenCalledTimes(1);
      slow.resolve({ kind: 'ok', limitation: KNEE });
      await settle(fixture);
    });
  });

  describe('healed and current', () => {
    beforeEach(() => setup());

    it('marks a current entry as healed and shows the new order', async () => {
      api.updateLimitation.mockResolvedValue({
        kind: 'ok',
        limitation: { ...ACHILLES, status: 'healed' },
      });
      api.listLimitations.mockResolvedValue(ok(BACK, { ...ACHILLES, status: 'healed' }, KNEE));

      await click(labelled('Mark as healed: achilles tendon'));

      expect(api.updateLimitation).toHaveBeenCalledExactlyOnceWith('achilles', {
        status: 'healed',
      });
      expect(ids()).toEqual(['back', 'achilles', 'knee']);
      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe('Marked as healed.');
    });

    it('makes a healed entry current again', async () => {
      api.updateLimitation.mockResolvedValue({
        kind: 'ok',
        limitation: { ...KNEE, status: 'current' },
      });

      await click(labelled('Current again: knee'));

      expect(api.updateLimitation).toHaveBeenCalledExactlyOnceWith('knee', { status: 'current' });
      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe(
        'Marked as current again.',
      );
    });

    it('says when the entry is gone and fetches the list again', async () => {
      api.updateLimitation.mockResolvedValue({ kind: 'not_found' });
      api.listLimitations.mockResolvedValue(ok(BACK, KNEE));

      await click(labelled('Mark as healed: achilles tendon'));

      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe(
        'That entry does not exist any more.',
      );
      expect(ids()).toEqual(['back', 'knee']);
    });

    it('shows the server’s messages when the change is refused', async () => {
      api.updateLimitation.mockResolvedValue({
        kind: 'invalid',
        errors: ['Choose one of: current, healed.'],
        fields: { status: ['Choose one of: current, healed.'] },
      });

      await click(labelled('Mark as healed: achilles tendon'));

      expect(alerts()).toEqual(['Choose one of: current, healed.']);
    });

    it('tells the page when the session is gone', async () => {
      api.updateLimitation.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await click(labelled('Mark as healed: achilles tendon'));

      expect(gone).toBe(1);
    });

    it('says something went wrong when the request fails', async () => {
      api.updateLimitation.mockRejectedValue(new Error('offline'));

      await click(labelled('Mark as healed: achilles tendon'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });
  });

  describe('deleting', () => {
    beforeEach(() => setup());

    it('asks first and deletes nothing until the answer is yes', async () => {
      await click(labelled('Delete: achilles tendon'));

      expect(card('achilles').textContent).toContain('Delete this entry?');
      expect(api.deleteLimitation).not.toHaveBeenCalled();
    });

    it('goes back when the answer is cancel', async () => {
      await click(labelled('Delete: achilles tendon'));

      const cancel = Array.from(card('achilles').querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Cancel',
      );
      await click(cancel as HTMLButtonElement);

      expect(card('achilles').textContent).not.toContain('Delete this entry?');
      expect(api.deleteLimitation).not.toHaveBeenCalled();
    });

    it('deletes after yes and fetches the list again', async () => {
      api.deleteLimitation.mockResolvedValue({ kind: 'deleted' });
      api.listLimitations.mockResolvedValue(ok(BACK, KNEE));
      await click(labelled('Delete: achilles tendon'));

      const yes = Array.from(card('achilles').querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Yes, delete',
      );
      await click(yes as HTMLButtonElement);

      expect(api.deleteLimitation).toHaveBeenCalledExactlyOnceWith('achilles');
      expect(ids()).toEqual(['back', 'knee']);
      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe(
        'The entry was deleted.',
      );
    });

    it('says when the entry was gone already', async () => {
      api.deleteLimitation.mockResolvedValue({ kind: 'not_found' });
      api.listLimitations.mockResolvedValue(ok(BACK, KNEE));
      await click(labelled('Delete: achilles tendon'));

      const yes = Array.from(card('achilles').querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Yes, delete',
      );
      await click(yes as HTMLButtonElement);

      expect(panel.querySelector('[role="status"]')?.textContent?.trim()).toBe(
        'That entry does not exist any more.',
      );
    });

    it('shows a failed refresh above the list', async () => {
      api.deleteLimitation.mockResolvedValue({ kind: 'deleted' });
      api.listLimitations.mockRejectedValue(new Error('offline'));
      await click(labelled('Delete: achilles tendon'));

      const yes = Array.from(card('achilles').querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Yes, delete',
      );
      await click(yes as HTMLButtonElement);

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
    });
  });
});
