import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DashboardApi } from '../../core/dashboard/dashboard-api';
import {
  Dashboard,
  GetDashboardResult,
  NextWorkout,
  WeekFigures,
  WellnessSummary,
} from '../../core/dashboard/dashboard-models';
import { query, settle } from '../../testing/dom';
import { DashboardPage } from './dashboard-page';
import { HIDDEN_KEY } from './setup-checklist';

const MONDAY = '2026-11-09';

const NEXT: NextWorkout = {
  id: 'w1',
  day: '2026-11-14',
  sport: 'running',
  title: '<b>Easy</b> run',
  minutes: 90,
  zone_system: 'heart_rate',
  zone: 2,
  sent: true,
};

const FIGURES: WeekFigures = {
  planned_minutes: 240,
  done_minutes: 60,
  workouts_done: 1,
  workouts_total: 4,
  average_rpe: 5.5,
};

function dashboard(
  changes: Partial<Dashboard['week']> = {},
  rest: Partial<Omit<Dashboard, 'week'>> = {},
): Dashboard {
  return {
    week: {
      week_start: MONDAY,
      next_workout: NEXT,
      figures: FIGURES,
      close_week: null,
      ...changes,
    },
    season: null,
    main_goal: null,
    weeks: [],
    recent: [],
    usage: { calls: 0, input_tokens: 0, output_tokens: 0, days: 30 },
    setup: [],
    wellness: null,
    ...rest,
  };
}

describe('DashboardPage', () => {
  let fixture: ComponentFixture<DashboardPage>;
  let get: ReturnType<typeof vi.fn<() => Promise<GetDashboardResult>>>;

  async function open(first: Promise<GetDashboardResult>): Promise<HTMLElement> {
    get = vi.fn<() => Promise<GetDashboardResult>>().mockReturnValue(first);
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: DashboardApi, useValue: { get } }],
    });
    fixture = TestBed.createComponent(DashboardPage);
    fixture.detectChanges();
    await settle(fixture);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  const ok = (found: Dashboard): Promise<GetDashboardResult> =>
    Promise.resolve({ kind: 'ok', dashboard: found });

  function text(page: HTMLElement, selector: string): string {
    return (query(page, selector).textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  it('shows skeletons while it loads', () => {
    get = vi.fn<() => Promise<GetDashboardResult>>().mockReturnValue(new Promise(() => undefined));
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: DashboardApi, useValue: { get } }],
    });
    fixture = TestBed.createComponent(DashboardPage);
    fixture.detectChanges();

    const page: HTMLElement = fixture.nativeElement;
    expect(query(page, '[role=status]').querySelectorAll('.skeleton').length).toBeGreaterThan(0);
    expect(page.textContent).not.toContain('Loading…');
  });

  it('says so when it cannot load, and tries again', async () => {
    get = vi.fn<() => Promise<GetDashboardResult>>().mockRejectedValueOnce(new Error('offline'));
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: DashboardApi, useValue: { get } }],
    });
    fixture = TestBed.createComponent(DashboardPage);
    fixture.detectChanges();
    await settle(fixture);
    fixture.detectChanges();
    const page: HTMLElement = fixture.nativeElement;
    expect(query(page, '[role=alert]').textContent).toContain('could not be loaded');

    get.mockReturnValue(ok(dashboard()));
    query<HTMLButtonElement>(page, 'button').click();
    await settle(fixture);
    fixture.detectChanges();

    expect(get).toHaveBeenCalledTimes(2);
    expect(page.querySelector('[role=alert]')).toBeNull();
    expect(page.querySelector('[data-testid=next-workout]')).not.toBeNull();
  });

  it('sends a signed-out user to sign in', async () => {
    const page = await open(Promise.resolve({ kind: 'forbidden' }));

    expect(query(page, '[role=alert]').textContent).toContain('session has ended');
    expect(query(page, 'a').getAttribute('href')).toBe('/login');
  });

  describe('the get-started checklist', () => {
    const KEYS = [
      'profile',
      'training_time',
      'ai_coach',
      'intervals',
      'goal',
      'activities',
      'season',
      'first_week',
    ] as const;
    const setup = (done: readonly string[]) =>
      KEYS.map((key) => ({ key, done: done.includes(key), optional: key === 'intervals' }));
    const REQUIRED = KEYS.filter((key) => key !== 'intervals');

    afterEach(() => globalThis.localStorage.removeItem(HIDDEN_KEY));

    it('is shown while a required step is open', async () => {
      const page = await open(ok(dashboard({}, { setup: setup(['profile']) })));

      expect(query(page, '[data-testid=setup-count]').textContent?.trim()).toBe('1 of 7 done');
    });

    it('is not shown when the answer has no steps or all required ones are done', async () => {
      const empty = await open(ok(dashboard({}, { setup: [] })));
      expect(empty.querySelector('[data-testid=setup]')).toBeNull();
      expect(empty.querySelector('[data-testid=setup-show]')).toBeNull();
    });

    it('goes away when every required step is done, the optional one open', async () => {
      const page = await open(ok(dashboard({}, { setup: setup(REQUIRED) })));

      expect(page.querySelector('[data-testid=setup]')).toBeNull();
      expect(page.querySelector('[data-testid=setup-show]')).toBeNull();
    });

    it('is hidden on request, kept in the browser, and can be shown again', async () => {
      const page = await open(ok(dashboard({}, { setup: setup([]) })));

      query<HTMLButtonElement>(page, '[data-testid=setup] button').click();
      fixture.detectChanges();
      expect(page.querySelector('[data-testid=setup]')).toBeNull();
      expect(globalThis.localStorage.getItem(HIDDEN_KEY)).toBe('1');

      query<HTMLButtonElement>(page, '[data-testid=setup-show] button').click();
      fixture.detectChanges();
      expect(query(page, '[data-testid=setup]')).toBeTruthy();
      expect(globalThis.localStorage.getItem(HIDDEN_KEY)).toBeNull();
    });

    it('stays hidden in a later visit', async () => {
      globalThis.localStorage.setItem(HIDDEN_KEY, '1');

      const page = await open(ok(dashboard({}, { setup: setup([]) })));

      expect(page.querySelector('[data-testid=setup]')).toBeNull();
      expect(query(page, '[data-testid=setup-show]')).toBeTruthy();
    });
  });

  describe('the next workout', () => {
    it('shows the day, the title as text, the length, the zone and that it was sent', async () => {
      const page = await open(ok(dashboard()));

      expect(text(page, '[data-testid=next-day]')).toBe('Sat 14 Nov');
      expect(text(page, '[data-testid=next-title]')).toBe('<b>Easy</b> run');
      expect(page.querySelector('[data-testid=next-title] b')).toBeNull();
      expect(text(page, '[data-testid=next-details]')).toBe('1 h 30 min · Heart rate zone 2');
      expect(text(page, '[data-testid=next-sent]')).toBe('Sent to Intervals.icu');
      expect(page.querySelector('[data-testid=next-empty]')).toBeNull();
    });

    it('says that it is not at Intervals.icu', async () => {
      const page = await open(ok(dashboard({ next_workout: { ...NEXT, sent: false } })));

      expect(text(page, '[data-testid=next-not-sent]')).toBe('Not sent to Intervals.icu');
      expect(page.querySelector('[data-testid=next-sent]')).toBeNull();
    });

    it('leaves out the zone of a workout without one', async () => {
      const page = await open(
        ok(dashboard({ next_workout: { ...NEXT, zone_system: null, zone: null } })),
      );

      expect(text(page, '[data-testid=next-details]')).toBe('1 h 30 min');
    });

    it('offers to draft the week when there is no workout', async () => {
      const page = await open(ok(dashboard({ next_workout: null })));

      const empty = query(page, '[data-testid=next-empty]');
      expect(empty.textContent).toContain('This week is not planned yet.');
      expect(query(empty, 'a').getAttribute('href')).toBe('/planning');
      expect(query(empty, 'a').textContent).toContain('Draft the week');
    });
  });

  describe('the week', () => {
    it('shows the week in the subtitle', async () => {
      const page = await open(ok(dashboard()));

      expect(text(page, '[data-testid=subtitle]')).toBe('Week of 9 Nov – 15 Nov');
    });

    it('shows the three tiles with their bars', async () => {
      const page = await open(ok(dashboard()));

      const tiles = Array.from(page.querySelectorAll('app-stat-tile'));
      expect(tiles.map((tile) => text(tile as HTMLElement, '[data-testid=value]'))).toEqual([
        '1 h',
        '1 of 4',
        '5.5',
      ]);
      expect(text(tiles[0] as HTMLElement, '[data-testid=detail]')).toBe('of 4 h planned');
      const bars = page.querySelectorAll('[role=progressbar]');
      expect(Array.from(bars).map((bar) => bar.getAttribute('aria-valuenow'))).toEqual([
        '25',
        '25',
      ]);
    });

    it('has no bars and a dash for a week without anything', async () => {
      const page = await open(
        ok(
          dashboard({
            figures: {
              planned_minutes: 0,
              done_minutes: 0,
              workouts_done: 0,
              workouts_total: 0,
              average_rpe: null,
            },
          }),
        ),
      );

      expect(page.querySelector('[role=progressbar]')).toBeNull();
      const rpe = page.querySelectorAll('app-stat-tile')[2] as HTMLElement;
      expect(text(rpe, '[data-testid=value]')).toBe('–');
      expect(text(rpe, '[data-testid=detail]')).toBe('No activity rated yet');
    });
  });

  describe('the week to close', () => {
    it('has no hint unless a week waits to be closed', async () => {
      const page = await open(ok(dashboard()));

      expect(page.querySelector('[data-testid=close-week]')).toBeNull();
    });

    it('links to the review', async () => {
      const page = await open(ok(dashboard({ close_week: '2026-11-02' })));

      const hint = query(page, '[data-testid=close-week]');
      expect(hint.textContent).toContain('2 Nov – 8 Nov');
      expect(query(hint, 'a').getAttribute('href')).toBe('/review?week=2026-11-02');
      expect(query(hint, 'a').textContent).toContain('Close the week');
    });
  });

  describe('the season', () => {
    it('offers to plan one when there is none', async () => {
      const page = await open(ok(dashboard()));

      const empty = query(page, '[data-testid=season-empty]');
      expect(query(empty, 'a').getAttribute('href')).toBe('/season');
      expect(page.querySelector('[data-testid=season]')).toBeNull();
    });

    it('shows the phase and what the week aims for', async () => {
      const page = await open(
        ok(dashboard({}, { season: { phase: 'build', recovery: false, target_minutes: 270 } })),
      );

      expect(text(page, '[data-testid=season-phase]')).toBe('Build');
      expect(text(page, '[data-testid=season-aim]')).toContain('4 h 30 min');
      expect(page.querySelector('[data-testid=season-recovery]')).toBeNull();
      expect(page.querySelector('[data-testid=season-empty]')).toBeNull();
    });

    it('says that it is a recovery week', async () => {
      const page = await open(
        ok(dashboard({}, { season: { phase: 'base', recovery: true, target_minutes: 120 } })),
      );

      expect(text(page, '[data-testid=season-recovery]')).toBe('Recovery week');
    });
  });

  describe('the main goal', () => {
    const goal = {
      id: 'g1',
      title: '<i>My</i> 10k',
      kind: 'race' as const,
      target_date: '2027-01-02',
      weeks_left: 7,
      rating: 'ambitious' as const,
    };

    it('offers to set one when there is none', async () => {
      const page = await open(ok(dashboard()));

      const empty = query(page, '[data-testid=goal-empty]');
      expect(query(empty, 'a').getAttribute('href')).toBe('/goals');
    });

    it('shows the title as text, the date, the weeks left and the rating as the goals do', async () => {
      const page = await open(ok(dashboard({}, { main_goal: goal })));

      expect(text(page, '[data-testid=goal-title]')).toBe('<i>My</i> 10k');
      expect(page.querySelector('[data-testid=goal-title] i')).toBeNull();
      expect(text(page, '[data-testid=goal-when]')).toBe('Race · Sat 2 Jan · 7 weeks to go');
      expect(text(page, '[data-testid=goal-rating]')).toBe('Ambitious');
      expect(query(page, '[data-testid=goal-rating]').classList).toContain('text-info');
    });

    it.each([
      [1, '1 week to go'],
      [0, 'Less than a week to go'],
    ])('counts %s weeks left', async (weeks, said) => {
      const page = await open(ok(dashboard({}, { main_goal: { ...goal, weeks_left: weeks } })));

      expect(text(page, '[data-testid=goal-when]')).toContain(said);
    });

    it('leaves out the date and the weeks of a goal without them', async () => {
      const page = await open(
        ok(dashboard({}, { main_goal: { ...goal, target_date: null, weeks_left: null } })),
      );

      expect(text(page, '[data-testid=goal-when]')).toBe('Race');
    });

    it('says when it cannot be judged yet', async () => {
      const page = await open(ok(dashboard({}, { main_goal: { ...goal, rating: 'unknown' } })));

      expect(text(page, '[data-testid=goal-rating]')).toBe('Cannot be judged yet');
    });
  });

  describe('the coach', () => {
    it('offers to set it up when it has not been used', async () => {
      const page = await open(ok(dashboard()));

      const empty = query(page, '[data-testid=usage-empty]');
      expect(empty.textContent).toContain('last 30 days');
      expect(query(empty, 'a').getAttribute('href')).toBe('/settings/connections');
    });

    it('shows the calls and the tokens', async () => {
      const page = await open(
        ok(
          dashboard({}, { usage: { calls: 3, input_tokens: 12345, output_tokens: 678, days: 30 } }),
        ),
      );

      expect(text(page, '[data-testid=usage]')).toBe(
        '3 calls in the last 30 days · 12,345 tokens in, 678 out',
      );
      expect(page.querySelector('[data-testid=usage-empty]')).toBeNull();
    });

    it('counts one call as one call', async () => {
      const page = await open(
        ok(dashboard({}, { usage: { calls: 1, input_tokens: 5, output_tokens: 4, days: 30 } })),
      );

      expect(text(page, '[data-testid=usage]')).toContain('1 call in');
    });
  });

  describe('the last weeks', () => {
    const weeks = [
      { week_start: '2026-11-02', sports: [{ sport: 'running' as const, minutes: 120 }] },
      { week_start: '2026-11-09', sports: [] },
    ];

    it('says so when nothing was trained', async () => {
      const page = await open(ok(dashboard({}, { weeks: [{ week_start: MONDAY, sports: [] }] })));

      expect(text(page, '[data-testid=weeks-empty]')).toBe(
        'You have not trained in the last 8 weeks.',
      );
      expect(page.querySelector('app-minutes-chart')).toBeNull();
    });

    it('draws the chart with the weeks', async () => {
      const page = await open(ok(dashboard({}, { weeks })));

      expect(page.querySelectorAll('app-minutes-chart g[data-testid^=bar-]')).toHaveLength(2);
      expect(page.querySelector('[data-testid=weeks-empty]')).toBeNull();
    });
  });

  describe('the latest activities', () => {
    it('offers to add one when there is none', async () => {
      const page = await open(ok(dashboard()));

      const empty = query(page, '[data-testid=recent-empty]');
      expect(query(empty, 'a').getAttribute('href')).toBe('/activities');
      expect(page.querySelector('[data-testid=recent]')).toBeNull();
    });

    it('lists them with the sport, the day and the minutes', async () => {
      const page = await open(
        ok(
          dashboard(
            {},
            {
              recent: [
                { id: 'a1', day: '2026-11-13', sport: 'cycling', minutes: 75 },
                { id: 'a2', day: '2026-11-12', sport: 'other', minutes: null },
              ],
            },
          ),
        ),
      );

      const items = Array.from(page.querySelectorAll('[data-testid=recent-item]')).map((item) =>
        Array.from(item.querySelectorAll('span')).map((span) => (span.textContent ?? '').trim()),
      );
      expect(items).toEqual([
        ['Cycling', 'Fri 13 Nov', '1 h 15 min'],
        ['Other', 'Thu 12 Nov', 'no duration'],
      ]);
      expect(page.querySelector('[data-testid=recent-empty]')).toBeNull();
    });
  });

  describe('the wellness and readiness', () => {
    const wellness: WellnessSummary = {
      sleep: { recent: 450, baseline: 500, trend: 'down' },
      hrv: { recent: 55, baseline: 50, trend: 'up' },
      resting_hr: { recent: 54, baseline: 50, trend: 'up' },
      weight: { recent: 72.5, baseline: 72.5, trend: 'flat' },
      warning: true,
      warning_signals: ['low_sleep', 'high_resting_hr'],
    };

    it('shows the empty state when no wellness is synced', async () => {
      const page = await open(ok(dashboard()));

      expect(query(page, '[data-testid=wellness]')).toBeTruthy();
      expect(query(page, '[data-testid=wellness-empty]').textContent).toContain(
        'Connect Intervals.icu',
      );
      expect(page.querySelector('[data-testid=wellness-warning]')).toBeNull();
    });

    it('shows the metrics and the warning when recovery is worse than usual', async () => {
      const page = await open(ok(dashboard({}, { wellness })));

      expect(text(page, '[data-testid=wellness-sleep]')).toContain('7 h 30 min');
      expect(text(page, '[data-testid=wellness-resting_hr]')).toContain('54');
      expect(query(page, '[data-testid=wellness-warning]').getAttribute('role')).toBe('alert');
      expect(text(page, '[data-testid=wellness-warning-text]')).toContain(
        'sleep is shorter than usual',
      );
    });

    it('hides the warning when recovery is not clearly worse', async () => {
      const page = await open(
        ok(dashboard({}, { wellness: { ...wellness, warning: false, warning_signals: [] } })),
      );

      expect(page.querySelector('[data-testid=wellness-warning]')).toBeNull();
      expect(query(page, '[data-testid=wellness-sleep]')).toBeTruthy();
    });
  });
});
