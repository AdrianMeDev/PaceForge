import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DashboardApi } from '../../core/dashboard/dashboard-api';
import {
  Dashboard,
  GetDashboardResult,
  NextWorkout,
  WeekFigures,
} from '../../core/dashboard/dashboard-models';
import { query, settle } from '../../testing/dom';
import { DashboardPage } from './dashboard-page';

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

function dashboard(changes: Partial<Dashboard['week']> = {}): Dashboard {
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
      expect(query(hint, 'a').getAttribute('href')).toBe('/review');
      expect(query(hint, 'a').textContent).toContain('Close the week');
    });
  });
});
