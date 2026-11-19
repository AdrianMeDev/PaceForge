import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApiClient } from '../core/api/api-providers';
import { SeasonChangeReason } from '../core/season/season-models';
import { query } from '../testing/dom';
import { SeasonChangeNotice } from './season-change-notice';

const URL = '/api/season/reassessment/';
const PLANS = '/api/season/plans/';
const ID = '0195f3a0-0000-7000-8000-000000000001';
const OTHER_ID = '0195f3a0-0000-7000-8000-000000000002';
const HINT = { confirmed_plan_id: ID, reasons: ['goals_changed'], deviation_weeks: [] };
const EMPTY = { confirmed_plan_id: null, reasons: [], deviation_weeks: [] };
const VERSION = {
  id: ID,
  version: 4,
  status: 'confirmed',
  reason: 'Drafted by the coach',
  week_count: 12,
  created_at: '2026-10-01T10:00:00Z',
  confirmed_at: '2026-10-01T11:00:00Z',
};
const VERSIONS = {
  plans: [{ ...VERSION, id: OTHER_ID, version: 5, status: 'draft', confirmed_at: null }, VERSION],
};

describe('SeasonChangeNotice', () => {
  let fixture: ComponentFixture<SeasonChangeNotice>;
  let backend: HttpTestingController;
  let page: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideApiClient(), provideHttpClientTesting(), provideRouter([])],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(SeasonChangeNotice);
    page = fixture.nativeElement;
    fixture.detectChanges();
  });

  afterEach(() => {
    backend.expectNone((request) => request.method !== 'GET');
    backend.verify();
  });

  const take = (url = URL) => vi.waitFor(() => backend.expectOne(url));

  // Render after promise continuations, including while an older HTTP request is still pending.
  async function render(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    fixture.detectChanges();
  }

  async function show(body: object = HINT): Promise<void> {
    (await take()).flush(body);
    (await take(PLANS)).flush(VERSIONS);
    await render();
  }

  it.each<[SeasonChangeReason, string]>([
    ['baseline_unknown', 'original inputs of your confirmed season are unknown'],
    ['goals_changed', 'active goals have changed'],
    ['ftp_changed', 'effective cycling FTP has changed'],
    ['best_times_changed', 'best times have changed'],
    ['training_time_changed', 'available training time has changed substantially'],
    ['training_deviation', 'each of the latest three completed weeks was below 70% or above 130%'],
  ])('explains %s and names the confirmed version in its link', async (reason, text) => {
    await show({
      ...HINT,
      reasons: [reason],
      deviation_weeks:
        reason === 'training_deviation' ? ['2026-10-26', '2026-11-02', '2026-11-09'] : [],
    });

    expect(query(page, '[role="status"]').textContent).toContain(text);
    const link = query<HTMLAnchorElement>(page, 'a');
    expect(link.textContent).toContain('Ask for a change to confirmed version 4');
    expect(link.getAttribute('href')).toBe(`/season?change=${ID}#season-change`);
  });

  it('renders input hints alongside the deviation proposal', async () => {
    await show({
      ...HINT,
      reasons: ['goals_changed', 'training_deviation'],
      deviation_weeks: ['2026-10-26', '2026-11-02', '2026-11-09'],
    });
    expect(page.querySelectorAll('li')).toHaveLength(2);
    expect(page.textContent).toContain('Consider adjusting your season.');
  });

  it.each([EMPTY, { ...HINT, reasons: [] }])('hides without reasons: %j', async (body) => {
    expect(page.textContent?.trim()).toBe('');
    (await take()).flush(body);
    await render();
    expect(page.textContent?.trim()).toBe('');
    backend.expectNone(PLANS);
  });

  it('reloads reasons and the named version, then hides when a replacement fits', async () => {
    await show();
    void fixture.componentInstance.reload();
    await render();
    expect(page.querySelector('a')).toBeNull();
    (await take()).flush({ ...HINT, confirmed_plan_id: OTHER_ID, reasons: ['ftp_changed'] });
    (await take(PLANS)).flush({ plans: [{ ...VERSION, id: OTHER_ID, version: 6 }] });
    await render();
    expect(page.textContent).toContain('effective cycling FTP has changed');
    expect(query(page, 'a').getAttribute('href')).toBe(`/season?change=${OTHER_ID}#season-change`);
    expect(query(page, 'a').textContent).toContain('confirmed version 6');

    void fixture.componentInstance.reload();
    (await take()).flush(EMPTY);
    await render();
    expect(page.textContent?.trim()).toBe('');
  });

  it.each([401, 403])('clears a previous hint on session expiry (%i)', async (status) => {
    await show();
    void fixture.componentInstance.reload();
    (await take()).flush({}, { status, statusText: 'Forbidden' });
    await render();
    expect(page.textContent).toContain('Your session has ended.');
    expect(query(page, 'a').getAttribute('href')).toBe('/login');
    expect(page.querySelector('[data-testid="season-change-notice"]')).toBeNull();
  });

  it('reports session expiry while fetching the version name', async () => {
    (await take()).flush(HINT);
    (await take(PLANS)).flush({}, { status: 401, statusText: 'Unauthorized' });
    await render();
    expect(page.textContent).toContain('Your session has ended.');
  });

  it('offers retry when the status is unavailable and recovers without writing', async () => {
    (await take()).flush({}, { status: 503, statusText: 'Unavailable' });
    await render();
    expect(page.textContent).toContain('Season adjustment status is unavailable.');
    query<HTMLButtonElement>(page, 'button').click();
    await show();
    expect(page.textContent).toContain('confirmed version 4');
    expect(page.querySelector('button')).toBeNull();
  });

  it('clears an old hint when a refresh fails', async () => {
    await show();
    void fixture.componentInstance.reload();
    (await take()).error(new ProgressEvent('error'));
    await render();
    expect(page.querySelector('a')).toBeNull();
    expect(query(page, 'button').textContent).toBe('Retry');
  });

  it.each([
    { ...HINT, reasons: ['<script>bad</script>'] },
    { ...HINT, confirmed_plan_id: '../other-user' },
    { ...HINT, deviation_weeks: ['2026-11-02'] },
  ])('reports malformed reassessment as unavailable: %j', async (body) => {
    (await take()).flush(body);
    await render();
    expect(page.textContent).toContain('Season adjustment status is unavailable.');
    expect(page.querySelector('a')).toBeNull();
    expect(page.querySelector('script')).toBeNull();
    backend.expectNone(PLANS);
  });

  it.each([
    { plans: [] },
    { plans: [{ ...VERSION, id: OTHER_ID }] },
    { plans: [{ ...VERSION, status: 'superseded' }] },
    { plans: [{ ...VERSION, version: 'four' }] },
  ])('offers retry instead of linking to a missing or stale version: %j', async (body) => {
    (await take()).flush(HINT);
    (await take(PLANS)).flush(body);
    await render();
    expect(page.querySelector('a')).toBeNull();
    expect(query(page, 'button').textContent).toBe('Retry');
  });

  it.each(['hint', 'forbidden', 'failure'])(
    'ignores an older reassessment ending with %s',
    async (outcome) => {
      const older = await take();
      void fixture.componentInstance.reload();
      (await take()).flush(EMPTY);
      await render();
      if (outcome === 'failure') older.error(new ProgressEvent('error'));
      else older.flush(HINT, { status: outcome === 'forbidden' ? 403 : 200, statusText: 'Reply' });
      await render();
      expect(page.textContent?.trim()).toBe('');
      backend.expectNone(PLANS);
    },
  );

  it.each(['hint', 'forbidden', 'failure'])(
    'ignores an older version lookup ending with %s',
    async (outcome) => {
      (await take()).flush(HINT);
      const older = await take(PLANS);
      void fixture.componentInstance.reload();
      (await take()).flush(EMPTY);
      await render();
      if (outcome === 'failure') older.error(new ProgressEvent('error'));
      else
        older.flush(VERSIONS, { status: outcome === 'forbidden' ? 401 : 200, statusText: 'Reply' });
      await render();
      expect(page.textContent?.trim()).toBe('');
    },
  );

  it('ignores a reassessment after the notice is destroyed', async () => {
    const pending = await take();
    fixture.destroy();
    pending.flush(HINT);
    await new Promise((resolve) => setTimeout(resolve));
    backend.expectNone(PLANS);
  });
});
