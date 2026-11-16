import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { SeasonApi } from '../../core/season/season-api';
import {
  GetSeasonPlanResult,
  GetSeasonResult,
  ListSeasonPlansResult,
  Season,
  SeasonPlan,
  SeasonPlanVersion,
  SeasonRace,
  SeasonWeek,
} from '../../core/season/season-models';
import { query, settle } from '../../testing/dom';
import { SeasonPage } from './season-page';

const MAIN: SeasonRace = {
  date: '2027-02-28',
  priority: 'main',
  discipline: 'running',
  distance_m: 42195,
  title: 'Berlin Marathon',
};

function week(changes: Partial<SeasonWeek> = {}): SeasonWeek {
  return {
    week_start: '2026-11-16',
    phase: 'base',
    recovery: false,
    target_minutes: 240,
    capacity_minutes: 300,
    races: [],
    ...changes,
  };
}

const SEASON: Season = {
  rolling: false,
  truncated: false,
  main_race: MAIN,
  peak_minutes: 300,
  weeks: [
    week(),
    week({ week_start: '2026-11-23', recovery: true, target_minutes: 156 }),
    week({
      week_start: '2026-11-30',
      phase: 'specific',
      target_minutes: 300,
      races: [{ ...MAIN, priority: 'preparation', title: 'Park run', distance_m: 5000 }],
    }),
    week({ week_start: '2026-12-07', phase: 'taper', target_minutes: 135, races: [MAIN] }),
  ],
};
const ROLLING: Season = {
  ...SEASON,
  rolling: true,
  main_race: null,
  weeks: [week(), week({ week_start: '2026-11-23', phase: 'build' })],
};

function version(changes: Partial<SeasonPlanVersion> = {}): SeasonPlanVersion {
  return {
    id: '0195f3a0-0000-7000-8000-000000000001',
    version: 1,
    status: 'confirmed',
    reason: 'Drafted by the coach',
    week_count: 4,
    created_at: '2026-11-16T10:00:00Z',
    confirmed_at: '2026-11-16T10:05:00Z',
    ...changes,
  };
}

function plan(changes: Partial<SeasonPlan> = {}): SeasonPlan {
  return {
    ...version(),
    rationale: 'Base first, then the race.',
    parent: null,
    skeleton: SEASON,
    weeks: SEASON.weeks.map((skeleton, index) => ({
      week_start: skeleton.week_start,
      minutes: index === 3 ? { running: 90 } : { running: 120, cycling: 90 },
      total_minutes: index === 3 ? 90 : 210,
      focus: index === 3 ? 'race_specific' : 'endurance',
      key_sessions:
        index === 3
          ? [{ sport: 'running', kind: 'race', minutes: 60, detail: '' }]
          : [{ sport: 'running', kind: 'long', minutes: 90, detail: '3 x 10 min at tempo' }],
      reason: `Reason of week ${index + 1}.`,
    })),
    report: null,
    ...changes,
  };
}

describe('SeasonPage', () => {
  let fixture: ComponentFixture<SeasonPage>;
  let page: HTMLElement;
  let get: ReturnType<typeof vi.fn<() => Promise<GetSeasonResult>>>;
  let plans: ReturnType<typeof vi.fn<() => Promise<ListSeasonPlansResult>>>;
  let open: ReturnType<typeof vi.fn<(id: string) => Promise<GetSeasonPlanResult>>>;

  async function setup(first: GetSeasonResult | Error = { kind: 'ok', season: SEASON }) {
    get = vi.fn<() => Promise<GetSeasonResult>>();
    plans = vi
      .fn<() => Promise<ListSeasonPlansResult>>()
      .mockResolvedValue({ kind: 'ok', plans: [] });
    open = vi.fn<(id: string) => Promise<GetSeasonPlanResult>>();
    if (first instanceof Error) {
      get.mockRejectedValueOnce(first);
      get.mockResolvedValue({ kind: 'ok', season: SEASON });
    } else {
      get.mockResolvedValue(first);
    }
    TestBed.configureTestingModule({
      imports: [SeasonPage],
      providers: [provideRouter([]), { provide: SeasonApi, useValue: { get, plans, plan: open } }],
    });
    fixture = TestBed.createComponent(SeasonPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const rows = () => Array.from(page.querySelectorAll('tbody tr:not(.reason)'));
  const cells = (index: number) =>
    Array.from(rows()[index].querySelectorAll('th, td')).map((cell) =>
      cell.textContent?.replace(/\s+/g, ' ').trim(),
    );
  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ');

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      get = vi
        .fn<() => Promise<GetSeasonResult>>()
        .mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [SeasonPage],
        providers: [
          provideRouter([]),
          { provide: SeasonApi, useValue: { get, plans, plan: open } },
        ],
      });
      fixture = TestBed.createComponent(SeasonPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('table')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the season cannot be loaded', async () => {
      await setup(new Error('offline'));
      expect(text()).toContain('Your season could not be loaded.');

      query<HTMLButtonElement>(page, 'button.primary').click();
      await settle(fixture);

      expect(rows()).toHaveLength(4);
      expect(page.querySelector('[role="alert"]')).toBeNull();
    });

    it('says when the session is gone', async () => {
      await setup({ kind: 'forbidden' });

      expect(text()).toContain('Your session has ended.');
      expect(page.querySelector('table')).toBeNull();
    });
  });

  describe('a season with a race', () => {
    beforeEach(() => setup());

    it('names the main race, its day and the highest week', () => {
      const summary = query(page, '[data-testid="main-race"]').textContent?.replace(/\s+/g, ' ');

      expect(summary).toContain('A · Berlin Marathon · 42.2 km');
      expect(summary).toContain('Sun 28 Feb');
      expect(query(page, '[data-testid="peak"]').textContent).toBe('5 h');
    });

    it('has a row for every week with the week, the phase, the aim, the offer and the races', () => {
      expect(rows()).toHaveLength(4);
      expect(cells(0)).toEqual(['16 Nov – 22 Nov', 'Base', '4 h', '5 h', '']);
      expect(cells(3)).toEqual([
        '7 Dec – 13 Dec',
        'Taper',
        '2 h 15 min',
        '5 h',
        'A · Berlin Marathon · 42.2 km',
      ]);
    });

    it('marks a recovery week', () => {
      expect(cells(1)[1]).toBe('Base Recovery');
      expect(rows()[1].getAttribute('data-recovery')).toBe('true');
      expect(rows()[0].querySelector('[data-testid="recovery"]')).toBeNull();
    });

    it('shows a C race with its letter in its week', () => {
      expect(cells(2)[4]).toBe('C · Park run · 5 km');
    });

    it('says what the phases that occur are for, and only those', () => {
      const terms = Array.from(page.querySelectorAll('dt')).map((dt) => dt.textContent);

      expect(terms).toEqual(['Base', 'Specific', 'Taper']);
      expect(text()).toContain('Less volume, the intensity stays');
    });

    it('says that nothing is saved and that the numbers are a starting point', () => {
      expect(text()).toContain('worked out again every time you open this page; nothing is saved');
      expect(text()).toContain('The numbers are a starting point.');
    });

    it('says nothing about a missing race or a cut-off season', () => {
      expect(page.querySelector('[data-testid="no-race"]')).toBeNull();
      expect(page.querySelector('[data-testid="truncated"]')).toBeNull();
    });
  });

  describe('a season without a race', () => {
    beforeEach(() => setup({ kind: 'ok', season: ROLLING }));

    it('says so and points to the goals', () => {
      const note = query(page, '[data-testid="no-race"]');

      expect(note.textContent?.replace(/\s+/g, ' ')).toContain(
        'rolling skeleton of the next 2 weeks',
      );
      expect(query(note, 'a').getAttribute('href')).toBe('/goals');
      expect(page.querySelector('[data-testid="main-race"]')).toBeNull();
    });

    it('still lists the weeks', () => {
      expect(rows()).toHaveLength(2);
      expect(cells(1)[1]).toBe('Build');
    });
  });

  describe('a season that is cut off', () => {
    it('says that the last race lies more than a year away', async () => {
      await setup({ kind: 'ok', season: { ...SEASON, truncated: true } });

      expect(query(page, '[data-testid="truncated"]').textContent?.replace(/\s+/g, ' ')).toContain(
        'more than a year away. The skeleton stops after 4 weeks.',
      );
    });
  });

  describe('a week that offers nothing', () => {
    it('shows an aim and an offer of 0 min', async () => {
      await setup({
        kind: 'ok',
        season: { ...SEASON, weeks: [week({ target_minutes: 0, capacity_minutes: 0 })] },
      });

      expect(cells(0).slice(2, 4)).toEqual(['0 min', '0 min']);
    });
  });

  describe('without a plan of the coach', () => {
    it('looks as it did before: no plan columns, no versions', async () => {
      await setup();

      expect(plans).toHaveBeenCalledTimes(1);
      expect(open).not.toHaveBeenCalled();
      expect(page.querySelector('.versions')).toBeNull();
      expect(Array.from(page.querySelectorAll('thead th'))).toHaveLength(5);
    });
  });

  describe('with plans of the coach', () => {
    const CONFIRMED = version({ id: '0195f3a0-0000-7000-8000-000000000002', version: 2 });
    const DRAFT = version({
      id: '0195f3a0-0000-7000-8000-000000000003',
      version: 3,
      status: 'draft',
      confirmed_at: null,
    });
    const OLD = version({ status: 'superseded' });

    async function load(list: SeasonPlanVersion[], shown: SeasonPlan = plan()) {
      get = vi
        .fn<() => Promise<GetSeasonResult>>()
        .mockResolvedValue({ kind: 'ok', season: SEASON });
      plans = vi
        .fn<() => Promise<ListSeasonPlansResult>>()
        .mockResolvedValue({ kind: 'ok', plans: list });
      open = vi
        .fn<(id: string) => Promise<GetSeasonPlanResult>>()
        .mockResolvedValue({ kind: 'ok', plan: shown });
      TestBed.configureTestingModule({
        imports: [SeasonPage],
        providers: [
          provideRouter([]),
          { provide: SeasonApi, useValue: { get, plans, plan: open } },
        ],
      });
      fixture = TestBed.createComponent(SeasonPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
    }

    it('opens the confirmed version on its own', async () => {
      await load([DRAFT, CONFIRMED, OLD]);

      expect(open).toHaveBeenCalledExactlyOnceWith(CONFIRMED.id);
    });

    it('opens the newest draft if nothing is confirmed', async () => {
      await load([DRAFT, OLD]);

      expect(open).toHaveBeenCalledExactlyOnceWith(DRAFT.id);
    });

    it('opens nothing if there are only versions that were decided against', async () => {
      await load([version({ status: 'discarded' }), OLD]);

      expect(open).not.toHaveBeenCalled();
      expect(page.querySelectorAll('.versions li')).toHaveLength(2);
    });

    it('lists the versions with their status and marks the one that is shown', async () => {
      await load([DRAFT, CONFIRMED, OLD], plan({ id: CONFIRMED.id, version: 2 }));

      // the time of day depends on the time zone of the host, so only the words are compared
      const items = Array.from(page.querySelectorAll('.versions button')).map((item) =>
        item.textContent?.replace(/\s+/g, ' ').trim().split(' · ').slice(0, 2).join(' · '),
      );
      expect(items).toEqual(['Version 3 · Draft', 'Version 2 · Confirmed', 'Version 1 · Replaced']);
      expect(query(page, '[data-testid="version-2"]').getAttribute('aria-current')).toBe('true');
      expect(query(page, '[data-testid="version-3"]').getAttribute('aria-current')).toBeNull();
    });

    it('shows the plan of each week next to the skeleton', async () => {
      await load([CONFIRMED]);

      expect(
        Array.from(page.querySelectorAll('thead th')).map((th) => th.textContent?.trim()),
      ).toEqual([
        'Week',
        'Phase',
        'Aim',
        'Time on offer',
        'Races',
        'Plan',
        'Focus',
        'Key sessions',
      ]);
      expect(cells(0).slice(5)).toEqual([
        'Running 2 h · Cycling 1 h 30 min 3 h 30 min',
        'Endurance',
        'Running · Long · 1 h 30 min · 3 x 10 min at tempo',
      ]);
      expect(cells(3).slice(5)).toEqual([
        'Running 1 h 30 min 1 h 30 min',
        'Race specific',
        'Running · Race · 1 h',
      ]);
    });

    it('shows the reason of the week under it, and the rationale and status above', async () => {
      await load([CONFIRMED]);

      expect(query(page, '[data-testid="reason-0"]').textContent?.trim()).toBe('Reason of week 1.');
      expect(query(page, '[data-testid="rationale"]').textContent).toBe(
        'Base first, then the race.',
      );
      expect(
        query(page, '[data-testid="plan-status"]').textContent?.replace(/\s+/g, ' '),
      ).toContain('Showing version 1: Confirmed.');
    });

    it('shows the texts of the coach as text, never as markup', async () => {
      const text = '<img src=x onerror=alert(1)>';
      const shown = plan({ rationale: text });
      shown.weeks[0] = { ...shown.weeks[0], reason: text };
      shown.weeks[1] = {
        ...shown.weeks[1],
        key_sessions: [{ sport: 'running', kind: 'long', minutes: 60, detail: text }],
      };
      await load([CONFIRMED], shown);

      expect(page.querySelector('img')).toBeNull();
      expect(query(page, '[data-testid="rationale"]').textContent).toBe(text);
      expect(query(page, '[data-testid="reason-0"]').textContent).toContain(text);
      expect(page.querySelectorAll('[data-testid="plan-sessions"]')[1].textContent).toContain(text);
    });

    it('shows the skeleton of the version, not the one of today, and says so', async () => {
      const earlier = {
        ...SEASON,
        weeks: SEASON.weeks.slice(1),
      };
      const shown = plan({ skeleton: earlier, weeks: plan().weeks.slice(1) });
      await load([CONFIRMED], shown);

      expect(rows()).toHaveLength(3);
      expect(cells(0)[0]).toBe('23 Nov – 29 Nov');
      expect(query(page, '[data-testid="differs"]').textContent).toContain('earlier skeleton');
    });

    it('says nothing about a different skeleton when it is the same', async () => {
      await load([CONFIRMED]);

      expect(page.querySelector('[data-testid="differs"]')).toBeNull();
    });

    it('shows a week without minutes as empty', async () => {
      const shown = plan();
      shown.weeks[0] = { ...shown.weeks[0], minutes: {}, total_minutes: 0, key_sessions: [] };
      await load([CONFIRMED], shown);

      expect(cells(0).slice(5)).toEqual(['', 'Endurance', '']);
    });

    it('opens another version when it is chosen', async () => {
      await load([DRAFT, CONFIRMED]);
      open.mockResolvedValue({
        kind: 'ok',
        plan: plan({ id: DRAFT.id, version: 3, status: 'draft' }),
      });

      query<HTMLButtonElement>(page, '[data-testid="version-3"]').click();
      await settle(fixture);

      expect(open).toHaveBeenLastCalledWith(DRAFT.id);
      expect(query(page, '[data-testid="plan-status"]').textContent).toContain('Draft');
    });

    it('says when a version does not exist any more, and keeps the one that is shown', async () => {
      await load([DRAFT, CONFIRMED]);
      open.mockResolvedValue({ kind: 'not_found' });

      query<HTMLButtonElement>(page, '[data-testid="version-3"]').click();
      await settle(fixture);

      expect(query(page, '[data-testid="version-missing"]').textContent).toContain(
        'does not exist',
      );
      expect(query(page, '[data-testid="plan-status"]').textContent).toContain('version 1');
    });

    it('says when a version cannot be loaded', async () => {
      await load([DRAFT, CONFIRMED]);
      open.mockRejectedValue(new Error('offline'));

      query<HTMLButtonElement>(page, '[data-testid="version-3"]').click();
      await settle(fixture);

      expect(query(page, '[data-testid="version-problem"]').textContent).toContain(
        'could not be loaded',
      );
    });

    it('disables the versions while one is loading', async () => {
      await load([DRAFT, CONFIRMED]);
      let finish: (value: GetSeasonPlanResult) => void = () => undefined;
      open.mockReturnValue(new Promise((resolve) => (finish = resolve)));

      query<HTMLButtonElement>(page, '[data-testid="version-3"]').click();
      fixture.detectChanges();

      expect(query<HTMLButtonElement>(page, '[data-testid="version-2"]').disabled).toBe(true);
      finish({ kind: 'ok', plan: plan() });
      await settle(fixture);
      expect(query<HTMLButtonElement>(page, '[data-testid="version-2"]').disabled).toBe(false);
    });

    it('keeps the skeleton when the plans cannot be loaded, and offers a retry', async () => {
      await load([CONFIRMED]);
      plans.mockRejectedValueOnce(new Error('offline'));
      query<HTMLButtonElement>(page, '[data-testid="version-2"]'); // the page is there
      await (fixture.componentInstance as unknown as { load(): Promise<void> }).load();
      await settle(fixture);

      expect(rows()).toHaveLength(4);
      expect(query(page, '[data-testid="list-problem"]').textContent).toContain(
        'could not be loaded',
      );

      query<HTMLButtonElement>(page, '[data-testid="list-problem"] button').click();
      await settle(fixture);

      expect(page.querySelector('[data-testid="list-problem"]')).toBeNull();
      expect(rows()).toHaveLength(4);
    });

    it('says when the session is gone while the plans load', async () => {
      await load([CONFIRMED]);
      plans.mockResolvedValue({ kind: 'forbidden' });
      await (fixture.componentInstance as unknown as { load(): Promise<void> }).load();
      await settle(fixture);

      expect(text()).toContain('Your session has ended.');
    });
  });
});
