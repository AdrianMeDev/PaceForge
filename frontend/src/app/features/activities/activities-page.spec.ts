import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ActivitiesApi } from '../../core/activities/activities-api';
import {
  Activity,
  DeleteActivityResult,
  EnterActivityResult,
  ImportActivityResult,
  ListActivitiesResult,
  SyncActivitiesResult,
} from '../../core/activities/activities-models';
import { IntervalsConnectionApi } from '../../core/integrations/intervals-api';
import { GetConnectionResult, IntervalsConnection } from '../../core/integrations/intervals-models';
import { dayOf, query, required, settle, typeInto } from '../../testing/dom';
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
  avg_pace_s_per_km: null,
  avg_power_w: 325,
  total_ascent_m: 11,
  calories: 1133,
  training_load: null,
  manufacturer: 'coros',
  rpe: null,
  notes: '',
  load: null,
  load_source: null,
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
const CONNECTION: IntervalsConnection = {
  status: 'connected',
  athlete_id: 'i123',
  connected_at: '2026-11-01T10:00:00Z',
  last_checked_at: '2026-11-01T10:00:00Z',
  last_sync_at: null,
  last_sync_error: '',
};
const CONNECTED: GetConnectionResult = { kind: 'connected', connection: CONNECTION };
const SYNCED: Extract<SyncActivitiesResult, { kind: 'ok' }> = {
  kind: 'ok',
  imported: 0,
  skipped_duplicates: 0,
  skipped_strava: 0,
  skipped_invalid: 0,
  wellness_synced: 0,
  last_sync_at: '2026-11-19T12:30:00Z',
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
    syncFromIntervals: vi.fn<() => Promise<SyncActivitiesResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('ActivitiesPage', () => {
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
  let intervals: { get: ReturnType<typeof vi.fn<() => Promise<GetConnectionResult>>> };
  let fixture: ComponentFixture<ActivitiesPage>;
  let page: HTMLElement;
  let inputValue: string;

  beforeEach(() => {
    intervals = {
      get: vi.fn<() => Promise<GetConnectionResult>>().mockResolvedValue({ kind: 'not_connected' }),
    };
    TestBed.configureTestingModule({
      providers: [{ provide: IntervalsConnectionApi, useValue: intervals }],
    });
  });

  async function setup(
    first: ListActivitiesResult = ok([]),
    connection: GetConnectionResult | Promise<GetConnectionResult> = { kind: 'not_connected' },
  ) {
    api = createApiStub();
    api.list.mockResolvedValue(first);
    api.syncFromIntervals.mockResolvedValue(SYNCED);
    intervals.get.mockReturnValue(Promise.resolve(connection));
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

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
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

    it('says how many activities there are under the title', async () => {
      await setup(ok([RUN]));

      expect(query(page, '[data-testid=subtitle]').textContent).toBe('1 activity');
    });

    it('gives every value the name of its column, for the card of a phone', async () => {
      await setup(ok([RUN]));

      const labels = Array.from(rows()[0].querySelectorAll('td[data-label]')).map((cell) =>
        cell.getAttribute('data-label'),
      );
      expect(labels).toEqual([
        'Date',
        'Sport',
        'Duration',
        'Distance',
        'Avg. heart rate',
        'RPE',
        'Load',
        'Source',
      ]);
    });

    it('shows an empty state', async () => {
      await setup(ok([]));

      expect(text()).toContain('No activities yet.');
      expect(page.querySelector('table')).toBeNull();
      expect(page.querySelector('.paging')).toBeNull();
    });
  });

  describe('Intervals.icu sync', () => {
    const syncButton = () => button('Sync from Intervals.icu');
    const lastSync = () => query(page, '[data-testid="intervals-last-sync"]').textContent ?? '';
    const connectionLink = () => query<HTMLAnchorElement>(page, 'a[href="/settings/connections"]');

    it('offers sync, a last sync hint and the Strava note when connected', async () => {
      await setup(ok([]), CONNECTED);

      expect(intervals.get).toHaveBeenCalledExactlyOnceWith();
      expect(syncButton().disabled).toBe(false);
      expect(lastSync()).toContain('Never');
      expect(text()).toContain('Strava activities cannot be read');
      expect(api.syncFromIntervals).not.toHaveBeenCalled();
    });

    it('shows the previous successful sync time', async () => {
      await setup(ok([]), {
        kind: 'connected',
        connection: { ...CONNECTION, last_sync_at: '2026-11-15T09:00:00Z' },
      });

      expect(lastSync()).toContain(dayOf('2026-11-15T09:00:00Z'));
    });

    it('links to Connections when not connected', async () => {
      await setup();

      expect(connectionLink().textContent).toContain('Connect Intervals.icu');
      expect(text()).not.toContain('Sync from Intervals.icu');
      expect(text()).not.toContain('Strava activities cannot be read');
    });

    it('links to Connections for an invalid key and keeps the last sync hint', async () => {
      await setup(ok([]), {
        kind: 'connected',
        connection: { ...CONNECTION, status: 'invalid' },
      });

      expect(connectionLink().textContent).toContain('Update it');
      expect(text()).toContain('did not accept the stored key');
      expect(text()).not.toContain('Sync from Intervals.icu');
      expect(lastSync()).toContain('Never');
    });

    it('loads the list without waiting for connection status', async () => {
      const pending = deferred<GetConnectionResult>();
      await setup(ok([RUN]), pending.promise);

      expect(rows()).toHaveLength(1);
      expect(text()).not.toContain('Sync from Intervals.icu');
      expect(page.querySelector('a[href="/settings/connections"]')).toBeNull();

      pending.resolve(CONNECTED);
      await settle(fixture);

      expect(syncButton().disabled).toBe(false);
    });

    it('quietly keeps the activity list usable when connection status fails', async () => {
      intervals.get.mockRejectedValueOnce(new Error('offline'));
      await setup(ok([RUN]));

      expect(rows()).toHaveLength(1);
      expect(alerts()).toEqual([]);
      expect(query<HTMLInputElement>(page, '#file').disabled).toBe(false);
      expect(page.querySelector('a[href="/settings/connections"]')).toBeNull();
    });

    it('syncs only on click and reports all counts', async () => {
      await setup(ok([]), CONNECTED);
      api.syncFromIntervals.mockResolvedValue({
        ...SYNCED,
        imported: 2,
        skipped_duplicates: 3,
        skipped_strava: 4,
        skipped_invalid: 5,
        wellness_synced: 6,
      });

      await click('Sync from Intervals.icu');

      expect(api.syncFromIntervals).toHaveBeenCalledExactlyOnceWith();
      expect(query(page, '.notice[role="status"]').textContent).toBe(
        'Intervals.icu sync: 2 imported; 3 duplicates skipped; 4 Strava activities skipped; 5 invalid activities skipped; 6 wellness days synced.',
      );
      expect(lastSync()).toContain(dayOf('2026-11-19T12:30:00Z'));
    });

    it('shows zero counts and leaves the list alone when nothing is imported', async () => {
      await setup(ok([RUN]), CONNECTED);

      await click('Sync from Intervals.icu');

      expect(query(page, '.notice').textContent).toContain(
        '0 imported; 0 duplicates skipped; 0 Strava activities skipped; 0 invalid activities skipped; 0 wellness days synced.',
      );
      expect(api.list).toHaveBeenCalledTimes(1);
      expect(rows()).toHaveLength(1);
      expect(lastSync()).toContain(dayOf('2026-11-19T12:30:00Z'));
    });

    it('refreshes page zero after imports from a later page', async () => {
      await setup(ok(many(20), 45), CONNECTED);
      api.list.mockResolvedValue(ok(many(20, 20), 45));
      await click('Next');
      api.syncFromIntervals.mockResolvedValue({ ...SYNCED, imported: 1 });
      api.list.mockResolvedValue(ok([{ ...RUN, source: 'intervals_icu' }, ...many(19)], 46));

      await click('Sync from Intervals.icu');

      expect(api.list).toHaveBeenLastCalledWith(20, 0);
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 46');
      expect(cells(rows()[0])[7]).toBe('Intervals.icu');
    });

    it('keeps the sport filter when refreshing after a sync', async () => {
      await setup(ok([RUN]), CONNECTED);
      await click('Running', query(page, '[data-testid="sport-filter"]'));
      api.syncFromIntervals.mockResolvedValue({ ...SYNCED, imported: 1 });

      await click('Sync from Intervals.icu');

      expect(api.list).toHaveBeenLastCalledWith(20, 0, 'running');
    });

    it('disables actions until both the sync and list refresh have finished', async () => {
      await setup(ok([RUN]), CONNECTED);
      const pending = deferred<SyncActivitiesResult>();
      const refresh = deferred<ListActivitiesResult>();
      api.syncFromIntervals.mockReturnValue(pending.promise);
      api.list.mockReturnValue(refresh.promise);

      syncButton().click();
      await settle(fixture);

      expect(syncButton().disabled).toBe(true);
      expect(query<HTMLInputElement>(page, '#file').disabled).toBe(true);
      expect(button('Save session').disabled).toBe(true);
      expect(button('Delete').disabled).toBe(true);
      syncButton().click();
      await choose(file('ignored.fit'));
      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
      expect(api.import).not.toHaveBeenCalled();

      pending.resolve({ ...SYNCED, imported: 1 });
      await settle(fixture);
      expect(syncButton().disabled).toBe(true);

      refresh.resolve(ok([RUN]));
      await settle(fixture);
      expect(syncButton().disabled).toBe(false);
      expect(query<HTMLInputElement>(page, '#file').disabled).toBe(false);
    });

    it('disables sync while files are importing', async () => {
      await setup(ok([]), CONNECTED);
      const pending = deferred<ImportActivityResult>();
      api.import.mockReturnValue(pending.promise);

      await choose(file('a.fit'));
      expect(syncButton().disabled).toBe(true);
      syncButton().click();
      expect(api.syncFromIntervals).not.toHaveBeenCalled();

      pending.resolve({ kind: 'duplicate', existingId: RUN.id });
      await settle(fixture);
      expect(syncButton().disabled).toBe(false);
    });

    it('disables sync while a page is being fetched', async () => {
      await setup(ok(many(20), 45), CONNECTED);
      const pending = deferred<ListActivitiesResult>();
      api.list.mockReturnValue(pending.promise);

      await click('Next');
      expect(syncButton().disabled).toBe(true);
      syncButton().click();
      expect(api.syncFromIntervals).not.toHaveBeenCalled();

      pending.resolve(ok(many(20, 20), 45));
      await settle(fixture);
      expect(syncButton().disabled).toBe(false);
    });

    it.each([
      ['not_connected', 'is no longer connected', 'Connect Intervals.icu'],
      ['invalid_key', 'did not accept the stored key', 'Update it'],
    ] as const)('handles a connection that becomes %s during sync', async (kind, error, link) => {
      await setup(ok([RUN]), CONNECTED);
      api.syncFromIntervals.mockResolvedValue({ kind });

      await click('Sync from Intervals.icu');

      expect(alerts()[0]).toContain(error);
      expect(connectionLink().textContent).toContain(link);
      expect(text()).not.toContain('Sync from Intervals.icu');
      expect(api.list).toHaveBeenCalledTimes(1);
      expect(rows()).toHaveLength(1);
    });

    it.each([
      [{ kind: 'rate_limited' }, 'Too many sync attempts. Please wait a minute and try again.'],
      [
        { kind: 'unavailable', message: 'Intervals.icu is temporarily unavailable.' },
        'Intervals.icu is temporarily unavailable.',
      ],
    ] satisfies [SyncActivitiesResult, string][])(
      'shows a %j error and allows retry',
      async (result, message) => {
        await setup(ok([RUN]), CONNECTED);
        api.syncFromIntervals.mockResolvedValueOnce(result);

        await click('Sync from Intervals.icu');

        expect(alerts()).toEqual([message]);
        expect(lastSync()).toContain('Never');
        expect(api.list).toHaveBeenCalledTimes(1);
        expect(syncButton().disabled).toBe(false);

        await click('Sync from Intervals.icu');

        expect(alerts()).toEqual([]);
        expect(query(page, '.notice').textContent).toContain('0 imported');
      },
    );

    it('shows a fallback error and keeps the last successful sync time on a failed request', async () => {
      await setup(ok([RUN]), {
        kind: 'connected',
        connection: { ...CONNECTION, last_sync_at: '2026-11-15T09:00:00Z' },
      });
      api.syncFromIntervals.mockRejectedValue(new Error('offline'));

      await click('Sync from Intervals.icu');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(lastSync()).toContain(dayOf('2026-11-15T09:00:00Z'));
      expect(syncButton().disabled).toBe(false);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('keeps the summary and updated sync time if refreshing the list fails', async () => {
      await setup(ok([RUN]), CONNECTED);
      api.syncFromIntervals.mockResolvedValue({ ...SYNCED, imported: 1 });
      api.list.mockRejectedValue(new Error('offline'));

      await click('Sync from Intervals.icu');

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
      expect(query(page, '.notice').textContent).toContain('1 imported');
      expect(lastSync()).toContain(dayOf('2026-11-19T12:30:00Z'));
      expect(rows()).toHaveLength(1);
      expect(syncButton().disabled).toBe(false);
    });

    it('shows the sign-in link if the sync finds an expired session', async () => {
      await setup(ok([RUN]), CONNECTED);
      api.syncFromIntervals.mockResolvedValue({ kind: 'forbidden' });

      await click('Sync from Intervals.icu');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(query(page, 'a').getAttribute('href')).toBe('/login');
      expect(api.list).toHaveBeenCalledTimes(1);
    });
  });

  describe('the drop zone', () => {
    /** A drop (or a drag) as the browser sends it, with the files it carries. */
    function drag(type: 'dragover' | 'dragleave' | 'drop', ...files: File[]): Event {
      const event = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(event, 'dataTransfer', { value: { files } });
      query(page, '[data-testid="drop-zone"]').dispatchEvent(event);
      return event;
    }

    it('imports dropped files one after the other, like chosen ones', async () => {
      await setup(ok([]));
      api.import.mockResolvedValue({ kind: 'imported', activity: RUN });

      const event = drag('drop', new File(['a'], 'a.fit'), new File(['b'], 'b.tcx'));
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
      expect(api.import.mock.calls.map(([sent]) => sent.name)).toEqual(['a.fit', 'b.tcx']);
      expect(results()).toHaveLength(2);
    });

    it('ignores a drop without files and one while an import runs', async () => {
      await setup(ok([]));
      let finish!: (result: ImportActivityResult) => void;
      api.import.mockReturnValue(new Promise<ImportActivityResult>((r) => (finish = r)));

      drag('drop');
      expect(api.import).not.toHaveBeenCalled();

      drag('drop', new File(['a'], 'a.fit'));
      await fixture.whenStable();
      drag('drop', new File(['b'], 'b.fit'));
      expect(api.import).toHaveBeenCalledTimes(1);

      finish({ kind: 'imported', activity: RUN });
      await settle(fixture);
    });

    it('is highlighted while files are over it, and not while it is busy', async () => {
      await setup(ok([]));
      const zone = () => query(page, '[data-testid="drop-zone"]');

      expect(drag('dragover').defaultPrevented).toBe(true);
      fixture.detectChanges();
      expect(zone().getAttribute('data-dragging')).toBe('true');

      drag('dragleave');
      fixture.detectChanges();
      expect(zone().getAttribute('data-dragging')).toBe('false');
    });
  });

  describe('the file input', () => {
    it('offers the formats the server reads, compressed ones too', async () => {
      await setup(ok([]));

      const input = query<HTMLInputElement>(page, '#file');

      expect(input.accept.split(',')).toEqual(['.fit', '.tcx', '.gpx', '.gz']);
      expect(input.multiple).toBe(true);
    });

    it('sends a compressed and a gpx file like any other', async () => {
      await setup(ok([]));
      api.import.mockResolvedValue({ kind: 'imported', activity: RUN });

      await choose(file('a.fit.gz'), file('b.gpx'));

      expect(api.import.mock.calls.map((call) => call[0].name)).toEqual(['a.fit.gz', 'b.gpx']);
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
        load: 53,
        load_source: 'rpe',
      };
      await setup(ok([lifting]));

      expect(cells(rows()[0]).slice(1, 8)).toEqual([
        'Strength',
        '45:00',
        '–',
        '–',
        '7',
        '53 pts (RPE estimate)',
        'Entered by hand',
      ]);
    });

    it('shows Intervals load without a rating, with its source context', async () => {
      await setup(
        ok([
          {
            ...RUN,
            source: 'intervals_icu',
            training_load: 75.4,
            load: 75,
            load_source: 'intervals',
          },
        ]),
      );

      expect(cells(rows()[0]).slice(5, 8)).toEqual([
        '–',
        '75 pts (Intervals.icu)',
        'Intervals.icu',
      ]);
    });

    it('shows zero load from Intervals and an RPE fallback on a synced activity', async () => {
      await setup(
        ok([
          { ...RUN, source: 'intervals_icu', training_load: 0, load: 0, load_source: 'intervals' },
          { ...BARE, source: 'intervals_icu', rpe: 6, load: 30, load_source: 'rpe' },
        ]),
      );

      expect(rows().map((row) => cells(row)[6])).toEqual([
        '0 pts (Intervals.icu)',
        '30 pts (RPE estimate)',
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
      load: 53,
      load_source: 'rpe',
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

      const dialog = query<HTMLDialogElement>(page, '[data-testid="confirm-dialog"]');
      expect(dialog.open).toBe(true);
      expect(dialog.textContent).toContain('Delete the Running of');
      expect(dialog.textContent).toContain('and the file stored with it, if there is one?');
      expect(api.delete).not.toHaveBeenCalled();
    });

    it('does nothing when cancelled', async () => {
      deleteButton('Running').click();
      await settle(fixture);

      query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-cancel"]').click();
      await settle(fixture);

      expect(api.delete).not.toHaveBeenCalled();
      expect(query<HTMLDialogElement>(page, '[data-testid="confirm-dialog"]').open).toBe(false);
      expect(rows()).toHaveLength(2);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('asks about one activity at a time', async () => {
      deleteButton('Running').click();
      await settle(fixture);
      deleteButton('Other (Rowing)').click();
      await settle(fixture);

      expect(page.querySelectorAll('[data-testid="confirm-dialog"]')).toHaveLength(1);
      expect(query(page, '[data-testid="confirm-dialog-message"]').textContent).toContain(
        'Delete the Other (Rowing) of',
      );
    });

    it('deletes the confirmed activity and refreshes the list', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok([BARE], 1));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Delete activity');

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

      const confirm = button('Delete activity');
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

      await click('Delete activity');

      expect(text()).toContain('The activity was already gone.');
      expect(rows()).toHaveLength(1);
    });

    it('says so when deleting does not work and keeps the list', async () => {
      api.delete.mockRejectedValue(new Error('offline'));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Delete activity');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(rows()).toHaveLength(2);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('shows the sign-in note when the session ended', async () => {
      api.delete.mockResolvedValue({ kind: 'forbidden' });
      deleteButton('Running').click();
      await settle(fixture);

      await click('Delete activity');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows the empty state after the last activity is deleted', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok([], 0));
      deleteButton('Running').click();
      await settle(fixture);

      await click('Delete activity');

      expect(text()).toContain('No activities yet.');
    });
  });

  describe('the sport filter', () => {
    const press = async (id: string) => {
      query<HTMLButtonElement>(page, `[data-testid="${id}"]`).click();
      await settle(fixture);
    };

    it('offers all and every sport, with all pressed first', async () => {
      await setup(ok([RUN]));

      const chips = Array.from(page.querySelectorAll('[data-testid="sport-filter"] button'));
      expect(chips.map((chip) => chip.textContent?.trim())).toEqual([
        'All',
        'Running',
        'Cycling',
        'Swimming',
        'Strength',
        'Other',
      ]);
      expect(query(page, '[data-testid="filter-all"]').getAttribute('aria-pressed')).toBe('true');
    });

    it('asks for one sport from the start and says which one is pressed', async () => {
      await setup(ok(many(20), 45));
      api.list.mockResolvedValue(ok([RUN], 1));

      await press('filter-running');

      expect(api.list).toHaveBeenLastCalledWith(20, 0, 'running');
      expect(query(page, '[data-testid="filter-running"]').getAttribute('aria-pressed')).toBe(
        'true',
      );
      expect(query(page, '[data-testid="filter-all"]').getAttribute('aria-pressed')).toBe('false');
    });

    it('keeps the sport while paging and goes back to the first page when it changes', async () => {
      await setup(ok(many(20), 45));
      api.list.mockResolvedValue(ok(many(20), 45));
      await press('filter-cycling');
      await click('Next');

      expect(api.list).toHaveBeenLastCalledWith(20, 20, 'cycling');

      await press('filter-swimming');

      expect(api.list).toHaveBeenLastCalledWith(20, 0, 'swimming');
    });

    it('shows all again without a sport', async () => {
      await setup(ok([RUN]));
      api.list.mockResolvedValue(ok([RUN], 1));
      await press('filter-running');

      await press('filter-all');

      expect(api.list.mock.calls.at(-1)).toEqual([20, 0]);
    });

    it('says when a sport has no activities, and keeps the filter to change it', async () => {
      await setup(ok([RUN]));
      api.list.mockResolvedValue(ok([], 0));

      await press('filter-swimming');

      expect(query(page, '[data-testid="filter-empty"]').textContent).toContain(
        'No swimming activities.',
      );
      expect(page.querySelector('table')).toBeNull();
      expect(query(page, '[data-testid="sport-filter"]')).toBeTruthy();
      expect(text()).not.toContain('No activities yet.');

      api.list.mockResolvedValue(ok([RUN], 1));
      await click('Show all');

      expect(rows()).toHaveLength(1);
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
      await click('Delete activity');

      expect(api.list.mock.calls).toEqual([
        [20, 20],
        [20, 0],
      ]);
      expect(query(page, '[data-testid="range"]').textContent).toBe('1–20 of 20');
    });
  });
});
