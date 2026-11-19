import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { JobsApi } from '../../core/jobs/jobs-api';
import {
  GetSettingsResult,
  JobRun,
  JobSettings,
  ListRunsResult,
  SaveSettingsResult,
  SettingsChanges,
} from '../../core/jobs/jobs-models';
import { query, settle } from '../../testing/dom';
import { AutomationPage } from './automation-page';

const SETTINGS: JobSettings = { sync: true, week_review: true, week_draft: true };

const RUN: JobRun = {
  id: 'sync-1',
  job: 'sync',
  week_start: null,
  started_at: '2026-11-12T21:07:49.046419Z',
  finished_at: '2026-11-12T21:07:50.046419Z',
  outcome: 'done',
  code: '',
  counts: { new_activities: 3 },
};

const SKIPPED: JobRun = {
  id: 'review-1',
  job: 'week_review',
  week_start: '2026-11-09',
  started_at: '2026-11-15T18:00:00Z',
  finished_at: '2026-11-15T18:00:05Z',
  outcome: 'skipped',
  code: 'already_planned',
  counts: {},
};

function createApiStub() {
  return {
    getSettings: vi.fn<() => Promise<GetSettingsResult>>(),
    saveSettings: vi.fn<(changes: SettingsChanges) => Promise<SaveSettingsResult>>(),
    listRuns: vi.fn<() => Promise<ListRunsResult>>(),
  };
}

describe('AutomationPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<AutomationPage>;
  let page: HTMLElement;

  async function setup(
    settings: GetSettingsResult = { kind: 'ok', settings: SETTINGS },
    runs: ListRunsResult = { kind: 'ok', runs: [SKIPPED, RUN] },
  ) {
    api = createApiStub();
    api.getSettings.mockResolvedValue(settings);
    api.listRuns.mockResolvedValue(runs);
    TestBed.configureTestingModule({
      imports: [AutomationPage],
      providers: [provideRouter([]), { provide: JobsApi, useValue: api }],
    });
    fixture = TestBed.createComponent(AutomationPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());

  function switchBox(key: keyof JobSettings): HTMLInputElement {
    return query<HTMLInputElement>(page, `#job-${key}`);
  }

  async function toggle(key: keyof JobSettings): Promise<void> {
    switchBox(key).click();
    await settle(fixture);
    fixture.detectChanges();
  }

  describe('loading', () => {
    it('shows a loading note until the state arrives', () => {
      api = createApiStub();
      api.getSettings.mockReturnValue(new Promise<never>(() => undefined));
      api.listRuns.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AutomationPage],
        providers: [provideRouter([]), { provide: JobsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AutomationPage);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
    });

    it('shows the three switches with their state', async () => {
      await setup({ kind: 'ok', settings: { sync: true, week_review: false, week_draft: true } });

      expect(switchBox('sync').checked).toBe(true);
      expect(switchBox('week_review').checked).toBe(false);
      expect(switchBox('week_draft').checked).toBe(true);
      expect(text()).toContain('Sync activities');
      expect(text()).toContain('Week review');
      expect(text()).toContain('Draft next week');
    });

    it('lists the runs with a fixed sentence for each code', async () => {
      await setup();

      expect(query(page, '[data-testid="run-review-1"]').textContent).toContain('Week review');
      expect(query(page, '[data-testid="run-review-1"]').textContent).toContain('Skipped');
      expect(query(page, '[data-testid="run-review-1"]').textContent).toContain(
        'Next week is already planned.',
      );
      expect(query(page, '[data-testid="run-sync-1"]').textContent).toContain('Sync activities');
      expect(query(page, '[data-testid="run-sync-1"]').textContent).toContain('Done');
      expect(query(page, '[data-testid="run-sync-1"]').textContent).toContain('new activities 3');
    });

    it('shows the week of a weekly run and a dash for a sync', async () => {
      await setup();

      expect(query(page, '[data-testid="run-review-1"]').textContent).toContain('9 Nov');
      expect(query(page, '[data-testid="run-sync-1"]').textContent).toContain('—');
    });

    it('shows an empty state when nothing has run yet', async () => {
      await setup({ kind: 'ok', settings: SETTINGS }, { kind: 'ok', runs: [] });

      expect(query(page, '[data-testid="no-runs"]').textContent).toContain('Nothing has run yet');
      expect(page.querySelector('[data-testid="runs"]')).toBeNull();
    });

    it('offers to try again when the state cannot be loaded', async () => {
      api = createApiStub();
      api.getSettings.mockRejectedValue(new Error('offline'));
      TestBed.configureTestingModule({
        imports: [AutomationPage],
        providers: [provideRouter([]), { provide: JobsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AutomationPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your automation settings could not be loaded.']);
      expect(query(page, 'button').textContent).toContain('Try again');
      expect(page.querySelector('#job-sync')).toBeNull();

      api.getSettings.mockResolvedValue({ kind: 'ok', settings: SETTINGS });
      api.listRuns.mockResolvedValue({ kind: 'ok', runs: [RUN] });
      query<HTMLButtonElement>(page, 'button').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(switchBox('sync').checked).toBe(true);
    });

    it('shows the signed-out state when only the log is forbidden', async () => {
      await setup({ kind: 'ok', settings: SETTINGS }, { kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('#job-sync')).toBeNull();
      expect(page.querySelector('[data-testid="no-runs"]')).toBeNull();
    });

    it('offers to try again when only the log cannot be loaded', async () => {
      api = createApiStub();
      api.getSettings.mockResolvedValue({ kind: 'ok', settings: SETTINGS });
      api.listRuns.mockRejectedValue(new Error('offline'));
      TestBed.configureTestingModule({
        imports: [AutomationPage],
        providers: [provideRouter([]), { provide: JobsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AutomationPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your automation settings could not be loaded.']);
    });

    it('shows the counts of a plain success without a leading bracket', async () => {
      await setup({ kind: 'ok', settings: SETTINGS }, { kind: 'ok', runs: [RUN] });

      const details = query(page, '[data-testid="run-sync-1"] .counts').textContent;
      expect(details).toBe('new activities 3');
    });

    it('sends a user whose session is gone to the sign-in page', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
    });
  });

  describe('saving a switch', () => {
    it.each<[keyof JobSettings]>([['sync'], ['week_review'], ['week_draft']])(
      'patches only %s when its switch is toggled',
      async (key) => {
        await setup();
        api.saveSettings.mockResolvedValue({
          kind: 'ok',
          settings: { ...SETTINGS, [key]: false },
        });

        await toggle(key);

        expect(api.saveSettings).toHaveBeenCalledExactlyOnceWith({ [key]: false });
        expect(switchBox(key).checked).toBe(false);
        expect(text()).toContain('Saved.');
      },
    );

    it('sends true when a switch that was off is turned on', async () => {
      await setup({ kind: 'ok', settings: { ...SETTINGS, sync: false } });
      api.saveSettings.mockResolvedValue({ kind: 'ok', settings: SETTINGS });

      await toggle('sync');

      expect(api.saveSettings).toHaveBeenCalledExactlyOnceWith({ sync: true });
      expect(switchBox('sync').checked).toBe(true);
    });

    it('shows a message and keeps the old state when the save fails', async () => {
      await setup();
      let fail: () => void = () => undefined;
      api.saveSettings.mockReturnValue(
        new Promise<SaveSettingsResult>(
          (_resolve, reject) => (fail = () => reject(new Error('offline'))),
        ),
      );

      switchBox('sync').click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(switchBox('sync').checked).toBe(false); // moved optimistically

      fail();
      await settle(fixture);

      expect(alerts()).toEqual(['The setting could not be saved. Please try again.']);
      expect(switchBox('sync').checked).toBe(true);
    });

    it('sends a user whose session is gone to the sign-in page', async () => {
      await setup();
      api.saveSettings.mockResolvedValue({ kind: 'forbidden' });

      await toggle('sync');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('keeps the other switch when two saves run at the same time and one fails', async () => {
      await setup();
      let failSync: () => void = () => undefined;
      let finishDraft: (result: SaveSettingsResult) => void = () => undefined;
      api.saveSettings
        .mockReturnValueOnce(
          new Promise<SaveSettingsResult>(
            (_resolve, reject) => (failSync = () => reject(new Error('offline'))),
          ),
        )
        .mockReturnValueOnce(new Promise((resolve) => (finishDraft = resolve)));

      switchBox('sync').click();
      await fixture.whenStable();
      fixture.detectChanges();
      switchBox('week_draft').click();
      await fixture.whenStable();
      fixture.detectChanges();

      failSync();
      await settle(fixture);
      expect(switchBox('sync').checked).toBe(true);
      expect(switchBox('week_draft').checked).toBe(false);

      finishDraft({ kind: 'ok', settings: { ...SETTINGS, sync: false, week_draft: false } });
      await settle(fixture);
      // The answer of the draft save must not carry the failed sync change back in.
      expect(switchBox('sync').checked).toBe(true);
      expect(switchBox('week_draft').checked).toBe(false);
    });

    it('puts the checkbox back itself when the save fails before the next render', async () => {
      await setup();
      api.saveSettings.mockRejectedValue(new Error('offline'));

      switchBox('sync').click();
      await settle(fixture);

      expect(switchBox('sync').checked).toBe(true);
      expect(alerts()).toEqual(['The setting could not be saved. Please try again.']);
    });

    it('ignores a second toggle of the same switch while the first save is running', async () => {
      await setup();
      let finish: (result: SaveSettingsResult) => void = () => undefined;
      api.saveSettings.mockReturnValue(new Promise((resolve) => (finish = resolve)));

      switchBox('week_draft').click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(switchBox('week_draft').disabled).toBe(true);

      switchBox('week_draft').click();
      await fixture.whenStable();

      expect(api.saveSettings).toHaveBeenCalledTimes(1);

      finish({ kind: 'ok', settings: { ...SETTINGS, week_draft: false } });
      await settle(fixture);
      expect(switchBox('week_draft').disabled).toBe(false);
    });
  });
});
