import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import { SeasonApi } from '../../core/season/season-api';
import {
  ConfirmSeasonResult,
  DiscardSeasonResult,
  GenerateSeasonResult,
  GetSeasonPlanResult,
  GetSeasonResult,
  ListSeasonPlansResult,
  RestoreSeasonResult,
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

const CONFIGURED: GetProviderResult = {
  kind: 'ok',
  state: { configured: true } as AiProviderState,
};
const NOT_CONFIGURED: GetProviderResult = {
  kind: 'ok',
  state: { configured: false } as AiProviderState,
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
      done: null,
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
  let generate: ReturnType<typeof vi.fn<() => Promise<GenerateSeasonResult>>>;
  let confirm: ReturnType<typeof vi.fn<(id: string) => Promise<ConfirmSeasonResult>>>;
  let restore: ReturnType<typeof vi.fn<(id: string) => Promise<RestoreSeasonResult>>>;
  let discard: ReturnType<typeof vi.fn<(id: string) => Promise<DiscardSeasonResult>>>;
  let provider: ReturnType<typeof vi.fn<() => Promise<GetProviderResult>>>;

  /** The stubs of the two APIs the page uses; `provider` says whether a coach is set up. */
  function providers() {
    return [
      provideRouter([]),
      {
        provide: SeasonApi,
        useValue: { get, plans, plan: open, generate, confirm, discard, restore },
      },
      { provide: CoachApi, useValue: { get: provider } },
    ];
  }

  async function setup(first: GetSeasonResult | Error = { kind: 'ok', season: SEASON }) {
    get = vi.fn<() => Promise<GetSeasonResult>>();
    plans = vi
      .fn<() => Promise<ListSeasonPlansResult>>()
      .mockResolvedValue({ kind: 'ok', plans: [] });
    open = vi.fn<(id: string) => Promise<GetSeasonPlanResult>>();
    generate = vi.fn<() => Promise<GenerateSeasonResult>>();
    confirm = vi.fn<(id: string) => Promise<ConfirmSeasonResult>>();
    discard = vi.fn<(id: string) => Promise<DiscardSeasonResult>>();
    restore = vi.fn<(id: string) => Promise<RestoreSeasonResult>>();
    provider = vi.fn<() => Promise<GetProviderResult>>().mockResolvedValue(CONFIGURED);
    if (first instanceof Error) {
      get.mockRejectedValueOnce(first);
      get.mockResolvedValue({ kind: 'ok', season: SEASON });
    } else {
      get.mockResolvedValue(first);
    }
    TestBed.configureTestingModule({
      imports: [SeasonPage],
      providers: providers(),
    });
    fixture = TestBed.createComponent(SeasonPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  beforeEach(() => {
    plans = vi
      .fn<() => Promise<ListSeasonPlansResult>>()
      .mockResolvedValue({ kind: 'ok', plans: [] });
    open = vi.fn<(id: string) => Promise<GetSeasonPlanResult>>();
    generate = vi.fn<() => Promise<GenerateSeasonResult>>();
    confirm = vi.fn<(id: string) => Promise<ConfirmSeasonResult>>();
    discard = vi.fn<(id: string) => Promise<DiscardSeasonResult>>();
    provider = vi.fn<() => Promise<GetProviderResult>>().mockResolvedValue(CONFIGURED);
  });

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
        providers: providers(),
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

    it('draws the timeline of the same weeks above the table', () => {
      const cells = Array.from(page.querySelectorAll('[data-testid="timeline-cell"]'));

      expect(cells).toHaveLength(4);
      expect(cells.map((cell) => cell.getAttribute('data-phase'))).toEqual([
        'base',
        'base',
        'specific',
        'taper',
      ]);
    });

    it('draws the chart of the aim of the skeleton above the table', () => {
      expect(page.querySelectorAll('svg [data-series="aim"]')).toHaveLength(4);
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
        providers: providers(),
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

    it('charts the plan by sport instead of the aim', async () => {
      await load([CONFIRMED]);

      expect(page.querySelector('svg [data-series="aim"]')).toBeNull();
      expect(page.querySelectorAll('svg [data-series="running"]')).toHaveLength(4);
      expect(page.querySelectorAll('svg [data-series="cycling"]')).toHaveLength(3);
    });

    it('adds a Done column and the narrow bars when the version has minutes done', async () => {
      const shown = plan({ id: CONFIRMED.id, version: 2 });
      shown.weeks[0] = {
        ...shown.weeks[0],
        done: [
          { sport: 'running', minutes: 60 },
          { sport: 'other', minutes: 30 },
        ],
      };
      shown.weeks[1] = { ...shown.weeks[1], done: [] };
      await load([CONFIRMED], shown);

      expect(Array.from(page.querySelectorAll('thead th')).pop()?.textContent?.trim()).toBe('Done');
      const done = Array.from(page.querySelectorAll('[data-testid="plan-done"]')).map((cell) =>
        cell.textContent?.replace(/\s+/g, ' ').trim(),
      );
      expect(done).toEqual(['Running 1 h · Other 30 min · 1 h 30 min in all', '0 min', '', '']);
      expect(page.querySelectorAll('svg rect.done')).toHaveLength(2);
    });

    it('has no Done column when no week has minutes done', async () => {
      await load([CONFIRMED]);

      expect(page.querySelector('[data-testid="plan-done"]')).toBeNull();
      expect(page.querySelector('svg rect.done')).toBeNull();
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

    describe('drafting', () => {
      const alerts = () =>
        Array.from(page.querySelectorAll('[role="alert"]')).map((alert) =>
          alert.textContent?.replace(/\s+/g, ' ').trim(),
        );
      const click = async (testId: string) => {
        query<HTMLButtonElement>(page, `[data-testid="${testId}"]`).click();
        await settle(fixture);
      };
      const DRAFT_PLAN = () =>
        plan({
          id: '0195f3a0-0000-7000-8000-000000000003',
          version: 3,
          status: 'draft',
          confirmed_at: null,
          report: { valid: true, findings: [] },
        });

      it('offers to draft the first version, and says what it costs', async () => {
        await load([]);

        expect(query(page, '[data-testid="generate"]').textContent?.trim()).toBe(
          'Draft the season with my coach',
        );
        expect(query(page, '[data-testid="cost"]').textContent).toContain('several times');
        expect(query(page, '[data-testid="cost"]').textContent).toContain('three tries');
      });

      it('offers a new version when there is one already', async () => {
        await load([CONFIRMED]);

        expect(query(page, '[data-testid="generate"]').textContent?.trim()).toBe(
          'Draft a new version',
        );
      });

      it('sends the user to the connections without a provider', async () => {
        provider = vi.fn<() => Promise<GetProviderResult>>().mockResolvedValue(NOT_CONFIGURED);
        await load([]);
        provider.mockResolvedValue(NOT_CONFIGURED);

        expect(page.querySelector('[data-testid="generate"]')).toBeNull();
        expect(query(query(page, '[data-testid="no-provider"]'), 'a').getAttribute('href')).toBe(
          '/settings/connections',
        );
      });

      it('shows the draft with its checks and refreshes the versions', async () => {
        await load([CONFIRMED], plan({ id: CONFIRMED.id, version: 2 }));
        const draft = {
          ...DRAFT_PLAN(),
          report: {
            valid: false,
            findings: [
              {
                severity: 'error' as const,
                code: 'minutes_outside_target',
                message: 'The week has 10 minutes; the skeleton aims for 240.',
                path: 'weeks[1].minutes',
              },
              { severity: 'warning' as const, code: 'race_week', message: 'No race.', path: '' },
            ],
          },
        };
        generate.mockResolvedValue({ kind: 'ok', plan: draft });
        plans.mockResolvedValue({ kind: 'ok', plans: [DRAFT, CONFIRMED] });

        await click('generate');

        expect(query(page, '.notice').textContent).toContain('A draft was made.');
        expect(page.querySelectorAll('.versions li')).toHaveLength(2);
        const findings = Array.from(page.querySelectorAll('.findings li')).map((item) =>
          item.textContent?.replace(/\s+/g, ' ').trim(),
        );
        expect(findings).toEqual([
          'Error · 23 Nov – 29 Nov: The week has 10 minutes; the skeleton aims for 240.',
          'Note · Season: No race.',
        ]);
      });

      it('says that the working takes a while, and allows nothing else meanwhile', async () => {
        await load([DRAFT, CONFIRMED], plan({ id: CONFIRMED.id, version: 2 }));
        let finish: (value: GenerateSeasonResult) => void = () => undefined;
        generate.mockReturnValue(new Promise((resolve) => (finish = resolve)));

        query<HTMLButtonElement>(page, '[data-testid="generate"]').click();
        fixture.detectChanges();

        expect(query(page, '[data-testid="generating"]').textContent).toContain('a few minutes');
        expect(query<HTMLButtonElement>(page, '[data-testid="generate"]').disabled).toBe(true);
        expect(query<HTMLButtonElement>(page, '[data-testid="version-3"]').disabled).toBe(true);
        finish({ kind: 'forbidden' });
        await settle(fixture);
      });

      it('asks only once while it works', async () => {
        await load([CONFIRMED]);
        generate.mockReturnValue(new Promise(() => undefined));

        const button = query<HTMLButtonElement>(page, '[data-testid="generate"]');
        button.click();
        button.click();
        await settle(fixture);

        expect(generate).toHaveBeenCalledTimes(1);
      });

      it('says when no week offers training time, and where to enter it', async () => {
        await load([]);
        generate.mockResolvedValue({ kind: 'no_time' });

        await click('generate');

        expect(alerts()).toEqual(['You have no training time in the weeks of your season.']);
        expect(query(query(page, '[data-testid="no-time"]'), 'a').getAttribute('href')).toBe(
          '/availability',
        );
      });

      it('says what was wrong when the coach gave nothing usable', async () => {
        await load([]);
        generate.mockResolvedValue({
          kind: 'not_usable',
          problems: [{ path: '', message: 'The answer is not one JSON object.' }],
        });

        await click('generate');

        expect(alerts()).toEqual([
          'The coach did not give a plan that could be used. Please try again.',
        ]);
        expect(query(page, '.problems').textContent).toContain(
          'The answer is not one JSON object.',
        );
      });

      it.each([
        [
          'the text of the provider with the time to wait',
          {
            kind: 'provider_problem',
            problem: 'rate_limited',
            message: 'Slow down.',
            retry_after: 17,
          },
          'Slow down. Try again in 17 seconds.',
        ],
        [
          'the text of the provider',
          { kind: 'provider_problem', problem: 'unavailable', message: 'Down.', retry_after: null },
          'Down.',
        ],
        [
          'a limit of this server',
          { kind: 'rate_limited' },
          'Too many requests. Please wait a minute and try again.',
        ],
      ] as [string, GenerateSeasonResult, string][])(
        'shows %s',
        async (_name, result, expected) => {
          await load([CONFIRMED]);
          generate.mockResolvedValue(result);

          await click('generate');

          expect(alerts()).toEqual([expected]);
          expect(query<HTMLButtonElement>(page, '[data-testid="generate"]').disabled).toBe(false);
        },
      );

      it('goes back to the hint when the provider is gone meanwhile', async () => {
        await load([CONFIRMED]);
        generate.mockResolvedValue({ kind: 'not_configured' });

        await click('generate');

        expect(page.querySelector('[data-testid="generate"]')).toBeNull();
        expect(page.querySelector('[data-testid="no-provider"]')).not.toBeNull();
      });

      it('says when the request fails, and stays usable', async () => {
        await load([CONFIRMED]);
        generate.mockRejectedValue(new Error('offline'));

        await click('generate');

        expect(alerts()).toEqual(['Something went wrong. Please try again.']);
        expect(rows()).toHaveLength(4);
        expect(query<HTMLButtonElement>(page, '[data-testid="generate"]').disabled).toBe(false);
      });

      it('says when the session is gone', async () => {
        await load([CONFIRMED]);
        generate.mockResolvedValue({ kind: 'forbidden' });

        await click('generate');

        expect(text()).toContain('Your session has ended.');
      });
    });

    describe('deciding', () => {
      const DRAFT_ID = '0195f3a0-0000-7000-8000-000000000003';
      const draft = (valid = true) =>
        plan({
          id: DRAFT_ID,
          version: 3,
          status: 'draft',
          confirmed_at: null,
          report: {
            valid,
            findings: valid
              ? []
              : [{ severity: 'error', code: 'x', message: 'Too much.', path: 'weeks[0].minutes' }],
          },
        });
      const DRAFT_VERSION = version({
        id: DRAFT_ID,
        version: 3,
        status: 'draft',
        confirmed_at: null,
      });
      const alerts = () =>
        Array.from(page.querySelectorAll('[role="alert"]')).map((alert) =>
          alert.textContent?.replace(/\s+/g, ' ').trim(),
        );
      const click = async (testId: string) => {
        query<HTMLButtonElement>(page, `[data-testid="${testId}"]`).click();
        await settle(fixture);
      };

      it('confirms a draft that the checks passed, and says what it replaces', async () => {
        await load([DRAFT_VERSION, CONFIRMED], draft());
        expect(query(page, '[data-testid="replaces"]').textContent).toContain('replaces version 2');
        confirm.mockResolvedValue({
          kind: 'ok',
          plan: {
            ...draft(),
            status: 'confirmed',
            report: null,
            confirmed_at: '2026-11-16T10:05:00Z',
          },
        });
        plans.mockResolvedValue({
          kind: 'ok',
          plans: [
            { ...DRAFT_VERSION, status: 'confirmed' },
            { ...CONFIRMED, status: 'superseded' },
          ],
        });

        await click('confirm');

        expect(confirm).toHaveBeenCalledExactlyOnceWith(DRAFT_ID);
        expect(query(page, '.notice').textContent).toContain('The plan is confirmed.');
        expect(page.querySelector('[data-testid="confirm"]')).toBeNull();
        expect(query(page, '[data-testid="plan-status"]').textContent).toContain('Confirmed');
        const labels = Array.from(page.querySelectorAll('.versions button')).map(
          (item) => item.textContent?.replace(/\s+/g, ' ').trim().split(' · ')[1],
        );
        expect(labels).toEqual(['Confirmed', 'Replaced']);
      });

      it('does not let a draft with errors be confirmed, and says why', async () => {
        await load([DRAFT_VERSION], draft(false));

        expect(query<HTMLButtonElement>(page, '[data-testid="confirm"]').disabled).toBe(true);
        expect(query(page, '[data-testid="cannot-confirm"]').textContent).toContain(
          'with errors cannot be confirmed',
        );
        expect(query(page, '.findings').textContent).toContain('Too much.');
        expect(query<HTMLButtonElement>(page, '[data-testid="discard"]').disabled).toBe(false);
      });

      it('shows what the server found when it refuses to confirm', async () => {
        await load([DRAFT_VERSION], draft());
        confirm.mockResolvedValue({
          kind: 'not_confirmable',
          findings: [{ severity: 'error', code: 'x', message: 'Not good.', path: '' }],
        });

        await click('confirm');

        expect(alerts()).toEqual(['The plan has errors and cannot be confirmed.']);
        expect(query(page, '.findings').textContent).toContain('Not good.');
        expect(query<HTMLButtonElement>(page, '[data-testid="confirm"]').disabled).toBe(true);
      });

      it('discards a draft and keeps the version in the list', async () => {
        await load([DRAFT_VERSION, CONFIRMED], draft());
        discard.mockResolvedValue({
          kind: 'ok',
          plan: { ...draft(), status: 'discarded', report: null },
        });
        plans.mockResolvedValue({
          kind: 'ok',
          plans: [{ ...DRAFT_VERSION, status: 'discarded' }, CONFIRMED],
        });

        await click('discard');

        expect(discard).toHaveBeenCalledExactlyOnceWith(DRAFT_ID);
        expect(query(page, '.notice').textContent).toContain('The draft was discarded.');
        expect(page.querySelector('[data-testid="discard"]')).toBeNull();
        expect(page.querySelectorAll('.versions li')).toHaveLength(2);
      });

      it.each(['confirm', 'discard'])('says when the draft is gone (%s)', async (action) => {
        await load([DRAFT_VERSION], draft());
        const gone = { kind: 'not_found' } as const;
        confirm.mockResolvedValue(gone);
        discard.mockResolvedValue(gone);
        plans.mockResolvedValue({ kind: 'ok', plans: [] });

        await click(action);

        expect(alerts()).toEqual(['That plan does not exist any more.']);
        expect(page.querySelector('[data-testid="plan-status"]')).toBeNull();
      });

      it.each(['confirm', 'discard'])(
        'reloads the plan when it is no draft any more (%s)',
        async (action) => {
          await load([DRAFT_VERSION], draft());
          const stale = { kind: 'not_a_draft' } as const;
          confirm.mockResolvedValue(stale);
          discard.mockResolvedValue(stale);
          open.mockResolvedValue({
            kind: 'ok',
            plan: { ...draft(), status: 'discarded', report: null },
          });

          await click(action);

          expect(alerts()).toEqual(['That plan is not a draft any more.']);
          expect(query(page, '[data-testid="plan-status"]').textContent).toContain('Discarded');
          expect(page.querySelector('[data-testid="confirm"]')).toBeNull();
        },
      );

      it.each(['confirm', 'discard'])('says when the request fails (%s)', async (action) => {
        await load([DRAFT_VERSION], draft());
        confirm.mockRejectedValue(new Error('offline'));
        discard.mockRejectedValue(new Error('offline'));

        await click(action);

        expect(alerts()).toEqual(['Something went wrong. Please try again.']);
        expect(query<HTMLButtonElement>(page, '[data-testid="discard"]').disabled).toBe(false);
      });

      it.each(['confirm', 'discard'])('says when the session is gone (%s)', async (action) => {
        await load([DRAFT_VERSION], draft());
        confirm.mockResolvedValue({ kind: 'forbidden' });
        discard.mockResolvedValue({ kind: 'forbidden' });

        await click(action);

        expect(text()).toContain('Your session has ended.');
      });

      it('has nothing to decide on a plan that is not a draft', async () => {
        await load([CONFIRMED], plan({ id: CONFIRMED.id, version: 2 }));

        expect(page.querySelector('[data-testid="confirm"]')).toBeNull();
        expect(page.querySelector('[data-testid="discard"]')).toBeNull();
      });
    });

    describe('restoring', () => {
      const OLD_ID = '0195f3a0-0000-7000-8000-000000000001';
      const NEW_ID = '0195f3a0-0000-7000-8000-000000000009';
      const REPLACED = version({ id: OLD_ID, version: 1, status: 'superseded' });
      const NOW_CONFIRMED = version({ id: NEW_ID, version: 2 });
      const alerts = () =>
        Array.from(page.querySelectorAll('[role="alert"]')).map((alert) =>
          alert.textContent?.replace(/\s+/g, ' ').trim(),
        );
      const click = async (testId: string) => {
        query<HTMLButtonElement>(page, `[data-testid="${testId}"]`).click();
        await settle(fixture);
      };
      const newDraft = (valid = true) =>
        plan({
          id: '0195f3a0-0000-7000-8000-000000000010',
          version: 3,
          status: 'draft',
          parent: OLD_ID,
          confirmed_at: null,
          report: {
            valid,
            findings: valid
              ? []
              : [{ severity: 'error', code: 'x', message: 'Too much.', path: 'weeks[0].minutes' }],
          },
        });

      async function openOld(status: 'superseded' | 'discarded' = 'superseded') {
        await load([NOW_CONFIRMED, { ...REPLACED, status }], plan({ id: NEW_ID, version: 2 }));
        open.mockResolvedValue({
          kind: 'ok',
          plan: plan({ id: OLD_ID, version: 1, status, confirmed_at: null, report: null }),
        });
        await click('version-1');
      }

      it.each(['superseded', 'discarded'] as const)(
        'offers to bring back a version that was %s',
        async (status) => {
          await openOld(status);

          expect(query(page, '[data-testid="restore"]').textContent?.trim()).toBe(
            'Make this the new draft',
          );
          expect(query(page, '[data-testid="restore-hint"]').textContent).toContain(
            'Restoring copies it as a new draft',
          );
        },
      );

      it('offers nothing for the confirmed version', async () => {
        await load([NOW_CONFIRMED], plan({ id: NEW_ID, version: 2 }));

        expect(page.querySelector('[data-testid="restore"]')).toBeNull();
      });

      it('offers nothing for a draft', async () => {
        await load(
          [version({ id: NEW_ID, version: 2, status: 'draft', confirmed_at: null })],
          plan({ id: NEW_ID, version: 2, status: 'draft', report: { valid: true, findings: [] } }),
        );

        expect(page.querySelector('[data-testid="restore"]')).toBeNull();
      });

      it('shows the new draft with its checks, says where it comes from and refreshes the list', async () => {
        await openOld();
        restore.mockResolvedValue({ kind: 'ok', plan: newDraft() });
        plans.mockResolvedValue({
          kind: 'ok',
          plans: [
            version({ id: newDraft().id, version: 3, status: 'draft', confirmed_at: null }),
            NOW_CONFIRMED,
            REPLACED,
          ],
        });

        await click('restore');

        expect(restore).toHaveBeenCalledExactlyOnceWith(OLD_ID);
        expect(query(page, '.notice').textContent).toContain(
          'Version 1 was restored as a new draft (version 3). Read it, then confirm it',
        );
        expect(query(page, '[data-testid="plan-status"]').textContent).toContain('Draft');
        expect(page.querySelectorAll('.versions li')).toHaveLength(3);
        expect(page.querySelector('[data-testid="restore"]')).toBeNull();
        expect(page.querySelector('[data-testid="confirm"]')).not.toBeNull();
      });

      it('says when the new draft has errors', async () => {
        await openOld();
        restore.mockResolvedValue({ kind: 'ok', plan: newDraft(false) });

        await click('restore');

        expect(query(page, '.notice').textContent).toContain(
          'It has errors and cannot be confirmed',
        );
        expect(query<HTMLButtonElement>(page, '[data-testid="confirm"]').disabled).toBe(true);
      });

      it('says that it works while it works and allows nothing else meanwhile', async () => {
        await openOld();
        let finish: (value: RestoreSeasonResult) => void = () => undefined;
        restore.mockReturnValue(new Promise((resolve) => (finish = resolve)));

        query<HTMLButtonElement>(page, '[data-testid="restore"]').click();
        fixture.detectChanges();

        expect(query(page, '[data-testid="restoring"]').textContent).toContain('Restoring');
        expect(query<HTMLButtonElement>(page, '[data-testid="restore"]').disabled).toBe(true);
        expect(query<HTMLButtonElement>(page, '[data-testid="generate"]').disabled).toBe(true);
        finish({ kind: 'forbidden' });
        await settle(fixture);
      });

      it('says when the version is gone', async () => {
        await openOld();
        restore.mockResolvedValue({ kind: 'not_found' });
        plans.mockResolvedValue({ kind: 'ok', plans: [NOW_CONFIRMED] });

        await click('restore');

        expect(alerts()).toEqual(['That plan does not exist any more.']);
        expect(page.querySelector('[data-testid="plan-status"]')).toBeNull();
      });

      it('says when it cannot be restored (any more) and shows it as it is', async () => {
        await openOld();
        restore.mockResolvedValue({ kind: 'not_restorable' });

        await click('restore');

        expect(alerts()).toEqual([
          'Only a version that was replaced or discarded can be restored.',
        ]);
        expect(open).toHaveBeenLastCalledWith(OLD_ID);
      });

      it('says when the request fails, and stays usable', async () => {
        await openOld();
        restore.mockRejectedValue(new Error('offline'));

        await click('restore');

        expect(alerts()).toEqual(['Something went wrong. Please try again.']);
        expect(query<HTMLButtonElement>(page, '[data-testid="restore"]').disabled).toBe(false);
        expect(rows()).toHaveLength(4);
      });

      it('says when the session is gone', async () => {
        await openOld();
        restore.mockResolvedValue({ kind: 'forbidden' });

        await click('restore');

        expect(text()).toContain('Your session has ended.');
      });
    });
  });
});
