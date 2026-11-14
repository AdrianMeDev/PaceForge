import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ActivitiesApi } from '../../core/activities/activities-api';
import {
  Activity,
  DeleteActivityResult,
  EnterActivityResult,
  ImportActivityResult,
  ListActivitiesResult,
} from '../../core/activities/activities-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { ActivitiesPage } from './activities-page';

const RUN: Activity = {
  id: 'a1',
  source: 'fit_file',
  sport: 'running',
  source_sport: 'running',
  start_time: '2026-10-13T10:10:45Z',
  elapsed_seconds: 3904.59,
  timer_seconds: 3900,
  distance_m: 12766.23,
  avg_heart_rate: 155,
  max_heart_rate: 169,
  avg_power_w: 325,
  total_ascent_m: 11,
  calories: 1133,
  manufacturer: 'coros',
  rpe: null,
  notes: '',
  load: null,
  created_at: '2026-11-13T07:29:55Z',
};
const BARE: Activity = {
  ...RUN,
  id: 'a2',
  source: 'tcx_file',
  sport: 'other',
  source_sport: 'Rowing',
  start_time: '2026-10-12T08:00:00Z',
  elapsed_seconds: 1800,
  timer_seconds: null,
  distance_m: null,
  avg_heart_rate: null,
};

const ok = (results: Activity[], count = results.length): ListActivitiesResult => ({
  kind: 'ok',
  page: { count, results },
});
const many = (n: number, from = 0): Activity[] =>
  Array.from({ length: n }, (_, i) => ({ ...RUN, id: `m${from + i}` }));

function createApiStub() {
  return {
    list: vi.fn<(limit: number, offset: number) => Promise<ListActivitiesResult>>(),
    get: vi.fn(),
    import: vi.fn<(file: File) => Promise<ImportActivityResult>>(),
    enter: vi.fn<() => Promise<EnterActivityResult>>(),
    delete: vi.fn<(id: string) => Promise<DeleteActivityResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('ActivitiesPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<ActivitiesPage>;
  let page: HTMLElement;
  let inputValue: string;

  async function setup(first: ListActivitiesResult = ok([])) {
    api = createApiStub();
    api.list.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [ActivitiesPage],
      providers: [provideRouter([]), { provide: ActivitiesApi, useValue: api }],
    });
    fixture = TestBed.createComponent(ActivitiesPage);
    page = fixture.nativeElement as HTMLElement;
    document.body.appendChild(page); // focus needs the element to be in the document
    await settle(fixture);
  }

  afterEach(() => page?.remove());

  const text = () => page.textContent ?? '';
  const rows = () => Array.from(page.querySelectorAll('tbody tr'));
  const cells = (row: Element) =>
    Array.from(row.querySelectorAll('td')).map((cell) => cell.textContent?.trim());
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const results = () =>
    Array.from(page.querySelectorAll('.results li')).map((e) =>
      (e.textContent ?? '').replace(/\s+/g, ' ').trim(),
    );

  function button(label: string, within: ParentNode = page): HTMLButtonElement {
    const match = Array.from(within.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string, within: ParentNode = page): Promise<void> {
    button(label, within).click();
    await settle(fixture);
  }

  const file = (name: string) => new File([new Uint8Array([1, 2])], name);

  /** Chooses files the way the browser reports them: `files` is set, `value` can be reset. */
  async function choose(...files: File[]): Promise<void> {
    const input = query<HTMLInputElement>(page, '#file');
    inputValue = 'C:\\fakepath\\chosen';
    Object.defineProperty(input, 'files', { value: files, configurable: true });
    Object.defineProperty(input, 'value', {
      get: () => inputValue,
      set: (value: string) => (inputValue = value),
      configurable: true,
    });
    input.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the list arrives', () => {
      api = createApiStub();
      api.list.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [ActivitiesPage],
        providers: [provideRouter([]), { provide: ActivitiesApi, useValue: api }],
      });
      fixture = TestBed.createComponent(ActivitiesPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('input')).toBeNull();
    });

    it('asks for the first page of 20', async () => {
      await setup();

      expect(api.list).toHaveBeenCalledExactlyOnceWith(20, 0);
    });

    it('offers a retry when the list cannot be loaded', async () => {
      api = createApiStub();
      api.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok([RUN]));
      TestBed.configureTestingModule({
        imports: [ActivitiesPage],
        providers: [provideRouter([]), { provide: ActivitiesApi, useValue: api }],
      });
      fixture = TestBed.createComponent(ActivitiesPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your activities could not be loaded.']);

      await click('Try again');

      expect(alerts()).toEqual([]);
      expect(rows()).toHaveLength(1);
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('input')).toBeNull();
    });

    it('shows an empty state', async () => {
      await setup(ok([]));

      expect(text()).toContain('No activities yet.');
      expect(page.querySelector('table')).toBeNull();
      expect(page.querySelector('.paging')).toBeNull();
    });
  });

  describe('the list', () => {
    it('shows what the files report and a dash for the rest', async () => {
      await setup(ok([RUN, BARE]));

      const [first, second] = rows();
      expect(cells(first).slice(1, 8)).toEqual([
        'Running',
        '1:05:00',
        '12.77 km',
        '155 bpm',
        '–',
        '–',
        'FIT',
      ]);
      expect(cells(second).slice(1, 8)).toEqual([
        'Other (Rowing)',
        '30:00',
        '–',
        '–',
        '–',
        '–',
        'TCX',
      ]);
    });

    it('shows the rating and the load of a session entered by hand', async () => {
      const lifting: Activity = {
        ...BARE,
        id: 'a3',
        source: 'manual',
        sport: 'strength',
        source_sport: '',
        timer_seconds: 2700,
        rpe: 7,
        notes: 'Legs were heavy',
        load: 315,
      };
      await setup(ok([lifting]));

      expect(cells(rows()[0]).slice(1, 8)).toEqual([
        'Strength',
        '45:00',
        '–',
        '–',
        '7',
        '315 AU',
        'Entered by hand',
      ]);
    });

    it('shows the start in the time zone of the browser', async () => {
      await setup(ok([RUN]));

      const shown = cells(rows()[0])[0] ?? '';
      const expected = new Intl.DateTimeFormat('en-US', {
        dateStyle: 'medium',
        timeStyle: 'medium',
      }).format(new Date(RUN.start_time));
      expect(shown.replace(/[\u202f\u00a0]/g, ' ')).toBe(
        expected.replace(/[\u202f\u00a0]/g, ' ').replace(',  ', ', '),
      );
    });

    it('uses the elapsed time when the file has no timer time', async () => {
      await setup(ok([BARE]));

      expect(cells(rows()[0])[2]).toBe('30:00');
    });

    it('shows the range', async () => {
      await setup(ok(many(3), 3));

      expect(query(page, '[data-testid="range"]').textContent).toBe('1–3 of 3');
    });
  });

  describe('paging', () => {
    it('moves to the next and the previous page', async () => {
      await setup(ok(many(20), 45));
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 45');
      expect(button('Previous').disabled).toBe(true);
      api.list.mockResolvedValue(ok(many(20, 20), 45));

      await click('Next');

      expect(api.list).toHaveBeenLastCalledWith(20, 20);
      expect(query(page, '[data-testid="range"]').textContent).toBe('21–40 of 45');
      expect(button('Previous').disabled).toBe(false);

      api.list.mockResolvedValue(ok(many(5, 40), 45));
      await click('Next');

      expect(api.list).toHaveBeenLastCalledWith(20, 40);
      expect(query(page, '[data-testid="range"]').textContent).toBe('41–45 of 45');
      expect(button('Next').disabled).toBe(true);

      api.list.mockResolvedValue(ok(many(20, 20), 45));
      await click('Previous');

      expect(api.list).toHaveBeenLastCalledWith(20, 20);
    });

    it('shows the first page after an import, even from a later page', async () => {
      await setup(ok(many(20), 45));
      api.list.mockResolvedValue(ok(many(20, 20), 45));
      await click('Next');
      expect(query(page, '[data-testid="range"]').textContent).toBe('21–40 of 45');
      api.import.mockResolvedValue({ kind: 'imported', activity: RUN });
      api.list.mockResolvedValue(ok(many(20), 46));

      await choose(file('a.fit'));

      expect(api.list).toHaveBeenLastCalledWith(20, 0);
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 46');
    });

    it('keeps the page and says so when a page cannot be loaded', async () => {
      await setup(ok(many(20), 45));
      api.list.mockRejectedValue(new Error('offline'));

      await click('Next');

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
      expect(rows()).toHaveLength(20);
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 45');
    });

    it('does not fetch a page twice at once', async () => {
      await setup(ok(many(20), 45));
      const pending = deferred<ListActivitiesResult>();
      api.list.mockReturnValue(pending.promise);

      button('Next').click();
      fixture.detectChanges();
      button('Next').click();
      pending.resolve(ok(many(20, 20), 45));
      await settle(fixture);

      expect(api.list).toHaveBeenCalledTimes(2); // the first page, then one more
    });
  });

  describe('importing', () => {
    beforeEach(() => setup(ok([])));

    it('sends the files one after the other, in order', async () => {
      const first = deferred<ImportActivityResult>();
      const second = deferred<ImportActivityResult>();
      api.import.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

      await choose(file('one.fit'), file('two.tcx'));

      expect(api.import).toHaveBeenCalledTimes(1);
      expect(api.import.mock.calls[0][0].name).toBe('one.fit');
      expect(text()).toContain('Importing one.fit');

      first.resolve({ kind: 'imported', activity: RUN });
      await settle(fixture);

      expect(api.import).toHaveBeenCalledTimes(2);
      expect(api.import.mock.calls[1][0].name).toBe('two.tcx');
      expect(text()).toContain('Importing two.tcx');

      second.resolve({ kind: 'imported', activity: BARE });
      await settle(fixture);

      expect(text()).not.toContain('Importing');
    });

    it('shows a result for each file and keeps going after a failure', async () => {
      api.import
        .mockRejectedValueOnce(new Error('offline'))
        .mockResolvedValueOnce({ kind: 'imported', activity: RUN })
        .mockResolvedValueOnce({ kind: 'duplicate', existingId: 'elsewhere' })
        .mockResolvedValueOnce({ kind: 'rejected', message: 'The file is damaged.' })
        .mockResolvedValueOnce({ kind: 'too_large' })
        .mockResolvedValueOnce({ kind: 'rate_limited' });

      await choose(
        file('a.fit'),
        file('b.fit'),
        file('c.fit'),
        file('d.tcx'),
        file('e.fit'),
        file('f.fit'),
      );

      expect(api.import).toHaveBeenCalledTimes(6);
      expect(results()).toEqual([
        'a.fit: Something went wrong. Please try again.',
        'b.fit: Imported (Running, 12.77 km).',
        'c.fit: Already imported.',
        'd.tcx: The file is damaged.',
        'e.fit: The file is too large.',
        'f.fit: Too many imports. Please wait a minute and try again.',
      ]);
    });

    it('marks each result by its kind', async () => {
      api.import
        .mockResolvedValueOnce({ kind: 'imported', activity: RUN })
        .mockResolvedValueOnce({ kind: 'rejected', message: 'No.' });

      await choose(file('a.fit'), file('b.fit'));

      const kinds = Array.from(page.querySelectorAll('.results li')).map((e) =>
        e.getAttribute('data-kind'),
      );
      expect(kinds).toEqual(['imported', 'rejected']);
    });

    it('sends nothing for an empty selection', async () => {
      await choose();

      expect(api.import).not.toHaveBeenCalled();
      expect(api.list).toHaveBeenCalledTimes(1);
      expect(page.querySelector('.results')).toBeNull();
    });

    it('keeps the earlier results when the selection is empty', async () => {
      api.import.mockResolvedValue({ kind: 'rejected', message: 'No.' });
      await choose(file('first.fit'));

      await choose();

      expect(results()).toEqual(['first.fit: No.']);
    });

    it('resets the input so that the same file can be chosen again', async () => {
      api.import.mockResolvedValue({ kind: 'rejected', message: 'No.' });

      await choose(file('same.fit'));

      expect(inputValue).toBe('');
      api.import.mockClear();

      await choose(file('same.fit'));

      expect(api.import).toHaveBeenCalledTimes(1);
    });

    it('ignores a new selection while files are being sent', async () => {
      const pending = deferred<ImportActivityResult>();
      api.import.mockReturnValue(pending.promise);
      await choose(file('one.fit'));
      expect(query<HTMLInputElement>(page, '#file').disabled).toBe(true);

      await choose(file('two.fit'));

      expect(api.import).toHaveBeenCalledTimes(1);
      pending.resolve({ kind: 'rejected', message: 'No.' });
      await settle(fixture);
      expect(query<HTMLInputElement>(page, '#file').disabled).toBe(false);
    });

    it('replaces the results of the last selection', async () => {
      api.import.mockResolvedValue({ kind: 'rejected', message: 'No.' });
      await choose(file('first.fit'));

      await choose(file('second.fit'));

      expect(results()).toEqual(['second.fit: No.']);
    });

    it('refreshes the list from the first page after an import', async () => {
      api.import.mockResolvedValue({ kind: 'imported', activity: RUN });
      api.list.mockResolvedValue(ok([RUN]));

      await choose(file('a.fit'), file('b.fit'));

      expect(api.list).toHaveBeenCalledTimes(2); // once on load, once after both files
      expect(api.list).toHaveBeenLastCalledWith(20, 0);
      expect(rows()).toHaveLength(1);
    });

    it('refreshes when any file was imported, not only the last one', async () => {
      api.import
        .mockResolvedValueOnce({ kind: 'imported', activity: RUN })
        .mockResolvedValueOnce({ kind: 'rejected', message: 'No.' });

      await choose(file('a.fit'), file('b.fit'));

      expect(api.list).toHaveBeenCalledTimes(2);
    });

    it('does not fetch the list again when nothing was imported', async () => {
      api.import
        .mockResolvedValueOnce({ kind: 'rejected', message: 'No.' })
        .mockResolvedValueOnce({ kind: 'duplicate', existingId: 'x' });

      await choose(file('a.fit'), file('b.fit'));

      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('keeps the results and says so when the refresh fails', async () => {
      api.import.mockResolvedValue({ kind: 'imported', activity: RUN });
      api.list.mockRejectedValue(new Error('offline'));

      await choose(file('a.fit'));

      expect(results()).toEqual(['a.fit: Imported (Running, 12.77 km).']);
      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
    });

    it('stops and shows the sign-in note when the session ended', async () => {
      api.import
        .mockResolvedValueOnce({ kind: 'imported', activity: RUN })
        .mockResolvedValueOnce({ kind: 'forbidden' });

      await choose(file('a.fit'), file('b.fit'), file('c.fit'));

      expect(api.import).toHaveBeenCalledTimes(2);
      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });
  });

  describe('entering a session by hand', () => {
    const ENTERED: Activity = {
      ...BARE,
      id: 'a9',
      source: 'manual',
      sport: 'strength',
      source_sport: '',
      timer_seconds: 2700,
      rpe: 7,
      load: 315,
    };

    async function fillAndSave(): Promise<void> {
      typeInto(page, '#manual-duration', '45');
      fixture.detectChanges();
      query<HTMLButtonElement>(page, '[data-testid="manual-save"]').click();
      await settle(fixture);
    }

    it('shows the form above the list, also when there are no activities yet', async () => {
      await setup(ok([]));

      expect(page.querySelector('app-manual-activity-form form')).not.toBeNull();
      expect(text()).toContain('or enter a session by hand');
    });

    it('fetches the newest activities again after a session was saved', async () => {
      await setup(ok(many(25), 25));
      api.enter.mockResolvedValue({ kind: 'entered', activity: ENTERED });
      api.list.mockResolvedValue(ok([ENTERED, ...many(19)], 26));

      await fillAndSave();

      expect(api.enter).toHaveBeenCalledTimes(1);
      expect(api.list).toHaveBeenLastCalledWith(20, 0);
      expect(cells(rows()[0]).slice(1, 8)).toContain('Entered by hand');
    });

    it('shows that the list could not be refreshed, and keeps the form working', async () => {
      await setup(ok([RUN]));
      api.enter.mockResolvedValue({ kind: 'entered', activity: ENTERED });
      api.list.mockRejectedValue(new Error('network'));

      await fillAndSave();

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
      expect(query(page, '[data-testid="manual-saved"]')).not.toBeNull();
    });

    it('goes to the sign-in when the session has ended', async () => {
      await setup(ok([RUN]));
      api.enter.mockResolvedValue({ kind: 'forbidden' });

      await fillAndSave();

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows the session the user has already when it is on the page', async () => {
      await setup(ok([RUN]));
      api.enter.mockResolvedValue({ kind: 'duplicate', existingId: RUN.id });

      await fillAndSave();
      query<HTMLButtonElement>(page, '[data-testid="manual-locate"]').click();
      await settle(fixture);

      expect(document.activeElement?.id).toBe(`activity-${RUN.id}`);
    });

    it('does not let the form start while a file is being imported', async () => {
      await setup(ok([RUN]));
      const pending = deferred<ImportActivityResult>();
      api.import.mockReturnValue(pending.promise);

      await choose(file('slow.fit'));

      expect(query<HTMLButtonElement>(page, '[data-testid="manual-save"]').disabled).toBe(true);
      pending.resolve({ kind: 'imported', activity: RUN });
      await settle(fixture);
    });
  });

  describe('a duplicate', () => {
    it('links to the row of the existing activity when it is in the list', async () => {
      await setup(ok([RUN, BARE]));
      api.import.mockResolvedValue({ kind: 'duplicate', existingId: 'a2' });

      await choose(file('again.fit'));
      await click('Show it in the list');

      const row = query(page, '#activity-a2');
      expect(document.activeElement).toBe(row);
      expect(row.getAttribute('data-highlight')).toBe('true');
      expect(query(page, '#activity-a1').getAttribute('data-highlight')).toBe('false');
    });

    it('has no link when the existing activity is on another page', async () => {
      await setup(ok([RUN]));
      api.import.mockResolvedValue({ kind: 'duplicate', existingId: 'elsewhere' });

      await choose(file('again.fit'));

      expect(results()).toEqual(['again.fit: Already imported.']);
      expect(text()).not.toContain('Show it in the list');
    });
  });

  describe('deleting', () => {
    beforeEach(() => setup(ok([RUN, BARE], 2)));

    const deleteButton = (sport: string) =>
      required(
        page.querySelector<HTMLButtonElement>(`button[aria-label^="Delete ${sport}"]`),
        `the delete button of ${sport}`,
      );

    it('asks first and deletes nothing until confirmed', async () => {
      deleteButton('Running').click();
      await settle(fixture);

      expect(text()).toContain('Delete this activity and its stored file, if it has one?');
      expect(api.delete).not.toHaveBeenCalled();
    });

    it('does nothing when cancelled', async () => {
      deleteButton('Running').click();
      await settle(fixture);

      await click('Cancel');

      expect(api.delete).not.toHaveBeenCalled();
      expect(text()).not.toContain('Delete this activity');
      expect(rows()).toHaveLength(2);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('asks about one activity at a time', async () => {
      deleteButton('Running').click();
      await settle(fixture);
      deleteButton('Other (Rowing)').click();
      await settle(fixture);

      expect(page.querySelectorAll('.confirm')).toHaveLength(1);
      expect(query(page, '.confirm').getAttribute('aria-label')).toBe('Delete Other (Rowing)');
    });

    it('deletes the confirmed activity and refreshes the list', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok([BARE], 1));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Yes, delete');

      expect(api.delete).toHaveBeenCalledExactlyOnceWith('a1');
      expect(rows()).toHaveLength(1);
      expect(cells(rows()[0])[1]).toBe('Other (Rowing)');
      expect(text()).toContain('The activity was deleted.');
      expect(api.list).toHaveBeenCalledTimes(2);
    });

    it('deletes only once when the button is clicked twice in a row', async () => {
      const pending = deferred<DeleteActivityResult>();
      api.delete.mockReturnValue(pending.promise);
      deleteButton('Running').click();
      await settle(fixture);

      const confirm = button('Yes, delete');
      confirm.click();
      confirm.click(); // before the page has been drawn again
      pending.resolve({ kind: 'deleted' });
      await settle(fixture);

      expect(api.delete).toHaveBeenCalledTimes(1);
    });

    it('treats an activity that is already gone as deleted', async () => {
      api.delete.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok([BARE], 1));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Yes, delete');

      expect(text()).toContain('The activity was already gone.');
      expect(rows()).toHaveLength(1);
    });

    it('says so when deleting does not work and keeps the list', async () => {
      api.delete.mockRejectedValue(new Error('offline'));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Yes, delete');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(rows()).toHaveLength(2);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('shows the sign-in note when the session ended', async () => {
      api.delete.mockResolvedValue({ kind: 'forbidden' });
      deleteButton('Running').click();
      await settle(fixture);

      await click('Yes, delete');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows the empty state after the last activity is deleted', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok([], 0));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Yes, delete');

      expect(text()).toContain('No activities yet.');
    });
  });

  describe('deleting the last activity of a page', () => {
    it('shows the new last page', async () => {
      await setup(ok(many(20), 21));
      api.list.mockResolvedValue(ok(many(1, 20), 21));
      await click('Next');
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockReset();
      api.list.mockResolvedValueOnce(ok([], 20)).mockResolvedValueOnce(ok(many(20), 20));

      page.querySelector<HTMLButtonElement>('button[aria-label^="Delete"]')?.click();
      await settle(fixture);
      await click('Yes, delete');

      expect(api.list.mock.calls).toEqual([
        [20, 20],
        [20, 0],
      ]);
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 20');
    });
  });
});
