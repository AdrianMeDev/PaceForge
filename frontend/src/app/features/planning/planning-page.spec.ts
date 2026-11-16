import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import { PlanningApi } from '../../core/planning/planning-api';
import {
  CheckPlanResult,
  ConfirmPlanResult,
  DiscardPlanResult,
  EditedPlan,
  Finding,
  GenerateResult,
  GetPlanResult,
  ListWeeksResult,
  PlanVersion,
  PlannableWeek,
  PushOutcome,
  PushPlanResult,
  RestorePlanResult,
  RevisePlanResult,
  WeekPlan,
  WorkoutExport,
} from '../../core/planning/planning-models';
import { query, settle } from '../../testing/dom';
import { PlanningPage } from './planning-page';

const NEXT = '2026-11-16';
const LATER = '2026-11-23';

const DRAFT_ID = '01a1d73d-2f26-7356-907e-f1475fc2aeab';
const OLD_ID = '01a1d73d-0000-7000-8000-000000000001';
const CONFIRMED_ID = '01a1d73d-6471-72e5-87a1-61b21e8ed49a';

const MISMATCH: Finding = {
  severity: 'error',
  code: 'segments_mismatch',
  message: 'The segments add up to 4200 seconds, the workout says 3600 seconds.',
  path: 'workouts[2].segments',
};
const NO_FREE_DAY: Finding = {
  severity: 'warning',
  code: 'no_free_day',
  message: 'The week has no day without a workout.',
  path: '',
};

function plan(changes: Partial<WeekPlan> = {}): WeekPlan {
  return {
    id: DRAFT_ID,
    week_start: NEXT,
    version: 2,
    status: 'draft',
    reason: 'Drafted by the coach',
    rationale: 'Base week with one tempo session.',
    parent: null,
    created_at: '2026-11-13T23:27:53.638352Z',
    confirmed_at: null,
    workouts: [
      {
        lineage: '01a1d73d-bbbb-7000-8000-000000000001',
        day: '2026-11-16',
        sport: 'cycling',
        title: 'Endurance ride',
        goal: 'endurance',
        duration_minutes: 60,
        zone_system: 'power',
        zone: 2,
        notes: 'Keep it easy',
        slot: null,
        stretching_minutes: 0,
        exercises: [],
        target: null,
        export: null,
        segments: [],
      },
      {
        lineage: '01a1d73d-bbbb-7000-8000-000000000002',
        day: '2026-11-16',
        sport: 'strength',
        title: 'Core',
        goal: 'strength',
        duration_minutes: 30,
        zone_system: null,
        zone: null,
        notes: '',
        slot: null,
        stretching_minutes: 0,
        exercises: [],
        target: null,
        export: null,
        segments: [],
      },
      {
        lineage: '01a1d73d-bbbb-7000-8000-000000000003',
        day: '2026-11-20',
        sport: 'running',
        title: 'Intervals',
        goal: 'threshold',
        duration_minutes: 70,
        zone_system: null,
        zone: null,
        notes: '',
        slot: null,
        stretching_minutes: 0,
        exercises: [],
        target: null,
        export: null,
        segments: [
          { kind: 'warmup', seconds: 900, repeat: 1, zone_system: 'pace', zone: 2, target: null },
          { kind: 'work', seconds: 600, repeat: 3, zone_system: 'pace', zone: 4, target: null },
        ],
      },
    ],
    report: { valid: false, findings: [MISMATCH] },
    export: null,
    ...changes,
  };
}

const WITH_ERRORS = plan();
const DOUBLE = plan({
  workouts: [
    {
      ...plan().workouts[0],
      title: 'Easy run',
      sport: 'running',
      slot: 'morning',
      stretching_minutes: 10,
      exercises: [],
      duration_minutes: 50,
    },
    { ...plan().workouts[0], title: 'Ride', slot: 'evening' },
    { ...plan().workouts[2], day: '2026-11-18' },
  ],
});

const VALID = plan({ report: { valid: true, findings: [] } });
const WARNED = plan({ report: { valid: true, findings: [NO_FREE_DAY] } });
const CONFIRMED = plan({
  id: CONFIRMED_ID,
  version: 1,
  status: 'confirmed',
  confirmed_at: '2026-11-13T23:28:07.353166Z',
  report: null,
});

const AT = '2026-11-14T08:00:00Z';
const SYNCED: WorkoutExport = { status: 'synced', error_code: '', pushed_at: AT };
const FAILED: WorkoutExport = { status: 'failed', error_code: 'rejected', pushed_at: AT };
const NOT_SENT: WorkoutExport = { status: 'not_sent', error_code: '', pushed_at: null };

/** A confirmed plan whose three workouts are in the given states. */
function sentPlan(states: [WorkoutExport, WorkoutExport, WorkoutExport], older = 0): WeekPlan {
  const count = (status: string) => states.filter((state) => state.status === status).length;
  return plan({
    id: CONFIRMED_ID,
    version: 1,
    status: 'confirmed',
    confirmed_at: '2026-11-13T23:28:07.353166Z',
    report: null,
    workouts: plan().workouts.map((workout, index) => ({ ...workout, export: states[index] })),
    export: {
      synced: count('synced'),
      failed: count('failed'),
      not_sent: count('not_sent'),
      older,
    },
  });
}

function version(changes: Partial<PlanVersion> = {}): PlanVersion {
  return {
    id: DRAFT_ID,
    version: 2,
    status: 'draft',
    reason: 'Drafted by the coach',
    workout_count: 3,
    created_at: '2026-11-13T23:27:53.638352Z',
    confirmed_at: null,
    ...changes,
  };
}

const OLD = version({ id: OLD_ID, version: 1, status: 'discarded' });
const CONFIRMED_VERSION = version({
  id: CONFIRMED_ID,
  version: 1,
  status: 'confirmed',
  confirmed_at: '2026-11-13T23:28:07.353166Z',
});

function weeks(next: PlanVersion[] = [version(), OLD], later: PlanVersion[] = []): PlannableWeek[] {
  return [
    { week_start: '2026-11-09', plans: [] },
    { week_start: NEXT, plans: next },
    { week_start: LATER, plans: later },
    { week_start: '2026-11-30', plans: [] },
    { week_start: '2026-12-07', plans: [] },
  ];
}

const ok = (list: PlannableWeek[] = weeks()): ListWeeksResult => ({ kind: 'ok', weeks: list });

function provider(configured: boolean): GetProviderResult {
  return { kind: 'ok', state: { configured } as AiProviderState };
}

function createStubs() {
  return {
    planning: {
      weeks: vi.fn<() => Promise<ListWeeksResult>>(),
      generate: vi.fn<(week: string) => Promise<GenerateResult>>(),
      get: vi.fn<(id: string) => Promise<GetPlanResult>>(),
      confirm: vi.fn<(id: string, push?: boolean) => Promise<ConfirmPlanResult>>(),
      push: vi.fn<(id: string) => Promise<PushPlanResult>>(),
      discard: vi.fn<(id: string) => Promise<DiscardPlanResult>>(),
      check: vi.fn<(week: string, plan: EditedPlan) => Promise<CheckPlanResult>>(),
      revise: vi.fn<(id: string, plan: EditedPlan) => Promise<RevisePlanResult>>(),
      restore: vi.fn<(id: string) => Promise<RestorePlanResult>>(),
    },
    coach: { get: vi.fn<() => Promise<GetProviderResult>>() },
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('PlanningPage', () => {
  let stubs: ReturnType<typeof createStubs>;
  let fixture: ComponentFixture<PlanningPage>;
  let page: HTMLElement;

  async function setup(
    options: {
      weeks?: ListWeeksResult;
      provider?: GetProviderResult;
      plans?: Record<string, GetPlanResult>;
    } = {},
  ) {
    stubs = createStubs();
    stubs.planning.weeks.mockResolvedValue(options.weeks ?? ok());
    stubs.coach.get.mockResolvedValue(options.provider ?? provider(true));
    const plans = options.plans ?? {
      [DRAFT_ID]: { kind: 'ok', plan: WITH_ERRORS },
      [OLD_ID]: {
        kind: 'ok',
        plan: plan({ id: OLD_ID, version: 1, status: 'discarded', report: null }),
      },
      [CONFIRMED_ID]: { kind: 'ok', plan: CONFIRMED },
    };
    stubs.planning.get.mockImplementation(async (id) => plans[id] ?? { kind: 'not_found' });
    stubs.planning.check.mockImplementation(async (_week, sent) => ({
      kind: 'ok',
      report: { valid: true, findings: [] },
      order: sent.workouts.map((_, index) => index),
    }));
    TestBed.configureTestingModule({
      imports: [PlanningPage],
      providers: [
        provideRouter([]),
        { provide: PlanningApi, useValue: stubs.planning },
        { provide: CoachApi, useValue: stubs.coach },
      ],
    });
    fixture = TestBed.createComponent(PlanningPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ');
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const byId = (id: string) => page.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const button = (id: string) => query<HTMLButtonElement>(page, `[data-testid="${id}"]`);
  const select = () => query<HTMLSelectElement>(page, '#plan-week');
  const notice = () => page.querySelector('.notice')?.textContent?.trim();

  async function choose(week: string) {
    select().value = week;
    select().dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function click(id: string) {
    button(id).click();
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a message while it waits', async () => {
      stubs = createStubs();
      const pending = deferred<ListWeeksResult>();
      stubs.planning.weeks.mockReturnValue(pending.promise);
      stubs.coach.get.mockResolvedValue(provider(true));
      TestBed.configureTestingModule({
        imports: [PlanningPage],
        providers: [
          provideRouter([]),
          { provide: PlanningApi, useValue: stubs.planning },
          { provide: CoachApi, useValue: stubs.coach },
        ],
      });
      fixture = TestBed.createComponent(PlanningPage);
      await fixture.whenStable();

      expect(fixture.nativeElement.textContent).toContain('Loading…');
    });

    it('offers to try again when the weeks cannot be loaded', async () => {
      await setup({ weeks: ok() });
      stubs.planning.weeks.mockRejectedValueOnce(new Error('down'));
      await fixture.componentInstance['load']();
      await settle(fixture);

      expect(alerts()).toEqual(['Your plans could not be loaded.']);

      query<HTMLButtonElement>(page, 'button.primary').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(select()).toBeTruthy();
    });

    it('offers to try again when the provider setup cannot be loaded', async () => {
      stubs = createStubs();
      stubs.planning.weeks.mockResolvedValue(ok());
      stubs.coach.get.mockRejectedValue(new Error('down'));
      TestBed.configureTestingModule({
        imports: [PlanningPage],
        providers: [
          provideRouter([]),
          { provide: PlanningApi, useValue: stubs.planning },
          { provide: CoachApi, useValue: stubs.coach },
        ],
      });
      fixture = TestBed.createComponent(PlanningPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your plans could not be loaded.']);
    });

    it.each([
      ['the weeks', { weeks: { kind: 'forbidden' } as ListWeeksResult }],
      ['the provider', { provider: { kind: 'forbidden' } as GetProviderResult }],
    ])('says when the session has ended (%s)', async (_name, options) => {
      await setup(options);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a[href="/login"]')).toBeTruthy();
    });
  });

  describe('the weeks', () => {
    it('lists the weeks and starts with next week', async () => {
      await setup();

      const labels = Array.from(select().options).map((option) => option.textContent?.trim());
      expect(labels).toEqual([
        '9 Nov – 15 Nov',
        '16 Nov – 22 Nov',
        '23 Nov – 29 Nov',
        '30 Nov – 6 Dec',
        '7 Dec – 13 Dec',
      ]);
      expect(select().value).toBe(NEXT);
    });

    it('starts with the only week if there is just one', async () => {
      await setup({ weeks: ok([{ week_start: '2026-11-09', plans: [] }]) });

      expect(select().value).toBe('2026-11-09');
    });

    it('works without any week', async () => {
      await setup({ weeks: ok([]) });

      expect(select().options.length).toBe(0);
      expect(stubs.planning.get).not.toHaveBeenCalled();
    });

    it('opens the newest draft or confirmed version of the week', async () => {
      await setup();

      expect(stubs.planning.get).toHaveBeenCalledExactlyOnceWith(DRAFT_ID);
      expect(text()).toContain('Version 2');
      expect(byId('status')?.textContent?.trim()).toBe('Draft');
    });

    it('skips discarded and replaced versions', async () => {
      await setup({
        weeks: ok(
          weeks([OLD, version({ id: 'x', version: 3, status: 'superseded' }), CONFIRMED_VERSION]),
        ),
      });

      expect(stubs.planning.get).toHaveBeenCalledExactlyOnceWith(CONFIRMED_ID);
    });

    it('opens nothing for a week with only discarded versions', async () => {
      await setup({ weeks: ok(weeks([OLD])) });

      expect(stubs.planning.get).not.toHaveBeenCalled();
      expect(byId('status')).toBeNull();
    });

    it('says there is no plan yet and offers the first draft', async () => {
      await setup({ weeks: ok(weeks([])) });

      expect(byId('no-plans')?.textContent).toContain('There is no plan for this week yet.');
      expect(button('generate').textContent?.trim()).toBe('Draft a plan with my coach');
    });

    it('offers a new version if there are versions already', async () => {
      await setup();

      expect(button('generate').textContent?.trim()).toBe('Draft a new version');
      expect(byId('no-plans')).toBeNull();
    });

    it('opens the plan of another week and drops the messages of the old one', async () => {
      await setup({
        weeks: ok(
          weeks([version(), OLD], [version({ id: CONFIRMED_ID, version: 1, status: 'confirmed' })]),
        ),
      });
      stubs.planning.generate.mockResolvedValue({ kind: 'rate_limited' });
      await click('generate');
      expect(alerts()).toHaveLength(1);

      await choose(LATER);

      expect(alerts()).toEqual([]);
      expect(select().value).toBe(LATER);
      expect(stubs.planning.get).toHaveBeenLastCalledWith(CONFIRMED_ID);
      expect(text()).toContain('Confirmed');
    });

    it('drops the notice of the old week as well', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'ok', plan: VALID });
      await click('generate');
      expect(notice()).toBeTruthy();

      await choose(LATER);

      expect(notice()).toBeUndefined();
    });

    it('shows no plan for a week that has none', async () => {
      await setup();

      await choose(LATER);

      expect(byId('status')).toBeNull();
      expect(byId('no-plans')).toBeTruthy();
    });

    it('ignores a week that is not in the list', async () => {
      await setup();
      stubs.planning.get.mockClear();

      await choose('2030-01-07');

      expect(stubs.planning.get).not.toHaveBeenCalled();
      expect(text()).toContain('Version 2');
    });

    it('lists the versions and opens another one', async () => {
      await setup();

      expect(byId('version-2')?.getAttribute('aria-current')).toBe('true');
      expect(byId('version-1')?.getAttribute('aria-current')).toBeNull();
      // The time depends on the time zone of the machine, so only its shape is checked.
      expect(byId('version-2')?.textContent?.replace(/\s+/g, ' ').trim()).toMatch(
        /^Version 2 · Draft · [A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$/,
      );

      await click('version-1');

      expect(stubs.planning.get).toHaveBeenLastCalledWith(OLD_ID);
      expect(byId('status')?.textContent?.trim()).toBe('Discarded');
      expect(byId('version-1')?.getAttribute('aria-current')).toBe('true');
      expect(byId('version-2')?.getAttribute('aria-current')).toBeNull();
    });
  });

  describe('a plan', () => {
    it('shows the workouts by day, with what they need', async () => {
      await setup();

      const days = Array.from(page.querySelectorAll('h3')).map((h) => h.textContent?.trim());
      expect(days).toEqual(['Mon 16 Nov', 'Fri 20 Nov']);
      const meta = (n: number) => byId(`workout-${n}`)?.querySelector('[data-testid="meta"]');
      expect(meta(1)?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 h · Power zone 2');
      expect(meta(2)?.textContent?.replace(/\s+/g, ' ').trim()).toBe('30 min');
      expect(byId('workout-1')?.textContent).toContain('Endurance ride');
      expect(byId('workout-1')?.textContent).toContain('Cycling');
      expect(byId('workout-1')?.textContent).toContain('Endurance');
      expect(byId('workout-1')?.textContent).toContain('Keep it easy');
    });

    it('puts two workouts of a day under one day', async () => {
      await setup();

      expect(page.querySelectorAll('h3')).toHaveLength(2);
      expect(page.querySelectorAll('.workout')).toHaveLength(3);
    });

    it('lists the parts of an interval workout', async () => {
      await setup();

      const parts = Array.from(byId('workout-3')?.querySelectorAll('.segments li') ?? []).map(
        (li) => li.textContent?.trim(),
      );
      expect(parts).toEqual(['15 min warm-up, pace zone 2', '3 × 10 min work, pace zone 4']);
      expect(byId('workout-1')?.querySelector('.segments')).toBeNull();
    });

    it('lists the exercises of a strength workout in order, with the numbers and what they train', async () => {
      const lifting = {
        ...plan().workouts[1],
        exercises: [
          {
            name: 'Goblet squat',
            region: 'legs' as const,
            equipment: 'dumbbells' as const,
            sets: 3,
            reps: 10,
            seconds: null,
            rpe: 7,
            rest_seconds: 90,
          },
          {
            name: 'Plank',
            region: 'core' as const,
            equipment: 'bodyweight' as const,
            sets: 3,
            reps: null,
            seconds: 45,
            rpe: null,
            rest_seconds: null,
          },
        ],
      };
      const withExercises = plan({ workouts: [plan().workouts[0], lifting, plan().workouts[2]] });
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: withExercises } } });

      const items = Array.from(byId('workout-2')?.querySelectorAll('.exercises li') ?? []).map(
        (li) => li.textContent?.replace(/\s+/g, ' ').trim(),
      );
      expect(items).toEqual([
        'Goblet squat 3 × 10 · RPE 7 · rest 1:30 Legs · Dumbbells',
        'Plank 3 × 45 s Core · Body weight',
      ]);
      expect(byId('workout-2')?.querySelector('ol.exercises')).not.toBeNull();
    });

    it('shows no list for a workout without exercises', async () => {
      await setup();

      expect(page.querySelector('.exercises')).toBeNull();
    });

    it('shows the rationale of the coach', async () => {
      await setup();

      expect(byId('rationale')?.textContent).toBe('Base week with one tempo session.');
    });

    it('leaves out an empty rationale', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: plan({ rationale: '' }) } } });

      expect(byId('rationale')).toBeNull();
    });

    it('shows text from the coach as text, never as markup', async () => {
      const hostile = plan({
        rationale: '<img src=x onerror=alert(1)>',
        workouts: [
          { ...plan().workouts[0], title: '<script>alert(1)</script>', notes: '<b>x</b>' },
        ],
      });
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: hostile } } });

      expect(page.querySelector('img, script, b')).toBeNull();
      expect(text()).toContain('<script>alert(1)</script>');
      expect(byId('rationale')?.textContent).toBe('<img src=x onerror=alert(1)>');
    });

    it('says so when a plan has no workouts', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: plan({ workouts: [] }) } } });

      expect(text()).toContain('The plan has no workouts.');
    });
  });

  describe('zones with numbers', () => {
    const base = plan();
    const WITH_TARGETS = plan({
      workouts: [
        { ...base.workouts[0], target: { low: 138, high: 188, unit: 'W' } },
        {
          ...base.workouts[2],
          segments: [
            { ...base.workouts[2].segments[0], target: { low: 312, high: 341, unit: 's/km' } },
            base.workouts[2].segments[1],
          ],
        },
      ],
    });

    beforeEach(() => setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: WITH_TARGETS } } }));

    it('shows the range next to the zone of a workout', () => {
      const meta = byId('workout-1')?.querySelector('[data-testid="meta"]');
      expect(meta?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 h · Power zone 2 · 138–188 W');
    });

    it('shows the range next to the zone of a segment, and none where there is none', () => {
      const parts = Array.from(byId('workout-2')?.querySelectorAll('.segments li') ?? []).map(
        (li) => li.textContent?.trim(),
      );
      expect(parts).toEqual([
        '15 min warm-up, pace zone 2 · 5:12–5:41 /km',
        '3 × 10 min work, pace zone 4',
      ]);
    });
  });

  describe('a day with two sessions and stretching', () => {
    beforeEach(() => setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: DOUBLE } } }));

    it('shows both sessions under one day, the morning first', () => {
      const days = Array.from(page.querySelectorAll('h3')).map((h) => h.textContent?.trim());
      expect(days).toEqual(['Mon 16 Nov', 'Wed 18 Nov']);
      const titles = Array.from(page.querySelectorAll('.workout h4')).map((h) => h.textContent);
      expect(titles).toEqual(['Easy run', 'Ride', 'Intervals']);
    });

    it('names the time of day of a session', () => {
      expect(byId('workout-1')?.querySelector('[data-testid="slot"]')?.textContent).toBe('Morning');
      expect(byId('workout-2')?.querySelector('[data-testid="slot"]')?.textContent).toBe('Evening');
    });

    it('names none for a session without one', () => {
      expect(byId('workout-3')?.querySelector('[data-testid="slot"]')).toBeNull();
    });

    it('shows stretching as an addition to the session and never as a session', () => {
      expect(byId('workout-1')?.querySelector('[data-testid="stretching"]')?.textContent).toBe(
        '+ 10 min stretching',
      );
      expect(page.querySelectorAll('.workout')).toHaveLength(3);
    });

    it('shows no stretching line for a session without it', () => {
      expect(byId('workout-2')?.querySelector('[data-testid="stretching"]')).toBeNull();
    });

    it('keeps the length of the session apart from the stretching', () => {
      const meta = byId('workout-1')?.querySelector('[data-testid="meta"]');

      expect(meta?.textContent?.replace(/\s+/g, ' ').trim()).toContain('50 min');
    });
  });

  describe('the checks', () => {
    it('puts a finding about the time of day at the session it is about', async () => {
      const flagged = plan({
        workouts: DOUBLE.workouts,
        report: {
          valid: false,
          findings: [
            {
              severity: 'error',
              code: 'same_slot',
              message: 'Monday has two workouts in the morning.',
              path: 'workouts[1].slot',
            },
          ],
        },
      });
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: flagged } } });

      expect(query(page, '.findings li').textContent?.replace(/\s+/g, ' ').trim()).toBe(
        'Error · Workout 2: Monday has two workouts in the morning.',
      );
    });

    it('show an error at the workout it is about', async () => {
      await setup();

      const items = Array.from(page.querySelectorAll('.findings li'));
      expect(items.map((li) => li.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
        'Error · Workout 3: The segments add up to 4200 seconds, the workout says 3600 seconds.',
      ]);
      expect(items[0].getAttribute('data-severity')).toBe('error');
    });

    it('show a note about the whole week', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: WARNED } } });

      const item = query(page, '.findings li');
      expect(item.textContent?.replace(/\s+/g, ' ').trim()).toBe(
        'Note · Week: The week has no day without a workout.',
      );
      expect(item.getAttribute('data-severity')).toBe('warning');
    });

    it('say when there is nothing to point out', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });

      expect(byId('all-clear')).toBeTruthy();
      expect(page.querySelector('.findings')).toBeNull();
    });

    it('are not shown for a plan that is decided on', async () => {
      await setup({ weeks: ok(weeks([CONFIRMED_VERSION])) });

      expect(byId('status')?.textContent?.trim()).toBe('Confirmed');
      expect(page.querySelector('.findings')).toBeNull();
      expect(byId('all-clear')).toBeNull();
    });
  });

  describe('without a provider', () => {
    it('points to the connections and offers nothing to ask', async () => {
      await setup({ provider: provider(false) });

      expect(byId('generate')).toBeNull();
      const link = query<HTMLAnchorElement>(page, '[data-testid="no-provider"] a');
      expect(link.getAttribute('href')).toBe('/settings/connections');
    });

    it('still shows the plans that exist', async () => {
      await setup({ provider: provider(false) });

      expect(text()).toContain('Version 2');
    });

    it('does not ask when told to', async () => {
      await setup({ provider: provider(false) });

      await fixture.componentInstance['generate']();

      expect(stubs.planning.generate).not.toHaveBeenCalled();
    });
  });

  describe('drafting', () => {
    it('asks for the selected week, says it takes a while and does one thing at a time', async () => {
      await setup();
      const pending = deferred<GenerateResult>();
      stubs.planning.generate.mockReturnValue(pending.promise);

      button('generate').click();
      await settle(fixture);

      expect(stubs.planning.generate).toHaveBeenCalledExactlyOnceWith(NEXT);
      expect(byId('generating')?.textContent).toContain('This can take a minute or two.');
      expect(button('generate').disabled).toBe(true);
      expect(select().disabled).toBe(true);
      expect(button('confirm').disabled).toBe(true);
      expect(button('discard').disabled).toBe(true);
      expect(byId('version-1')?.hasAttribute('disabled')).toBe(true);

      await fixture.componentInstance['generate']();
      await fixture.componentInstance['selectWeek'](LATER);
      await fixture.componentInstance['confirm']();
      await fixture.componentInstance['discard']();
      expect(stubs.planning.generate).toHaveBeenCalledTimes(1);
      await settle(fixture);
      expect(select().value).toBe(NEXT);
      expect(fixture.componentInstance['selected']()).toBe(NEXT);
      expect(stubs.planning.get).toHaveBeenCalledTimes(1); // the plan opened at the start

      pending.resolve({ kind: 'rate_limited' });
      await settle(fixture);

      expect(byId('generating')).toBeNull();
      expect(button('generate').disabled).toBe(false);
    });

    it('shows the new draft, tells the user to read it and refreshes the versions', async () => {
      await setup();
      const fresh = plan({ id: 'new', version: 3, report: { valid: true, findings: [] } });
      stubs.planning.generate.mockResolvedValue({ kind: 'ok', plan: fresh });
      stubs.planning.weeks.mockResolvedValue(
        ok(weeks([version({ id: 'new', version: 3 }), version(), OLD])),
      );

      await click('generate');

      expect(text()).toContain('Version 3');
      expect(notice()).toBe('A draft was made. Please read it before you confirm it.');
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
      expect(byId('version-3')?.getAttribute('aria-current')).toBe('true');
      expect(alerts()).toEqual([]);
    });

    it('says when the refresh of the versions fails', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'ok', plan: VALID });
      stubs.planning.weeks.mockRejectedValue(new Error('down'));

      await click('generate');

      expect(alerts()).toEqual(['The list of plans could not be refreshed. Please try again.']);
      expect(text()).toContain('Version 2');
    });

    it('says when the week cannot be planned (any more) and refreshes', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'not_plannable' });

      await click('generate');

      expect(alerts()).toEqual(['This week cannot be planned.']);
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('notices that the provider is gone', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'not_configured' });

      await click('generate');

      expect(byId('generate')).toBeNull();
      expect(byId('no-provider')).toBeTruthy();
    });

    it('says when the week offers no time and where to enter it', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'no_time' });

      await click('generate');

      expect(alerts()).toEqual(['You have no training time for this week.']);
      const link = query<HTMLAnchorElement>(page, '[data-testid="no-time"] a');
      expect(link.getAttribute('href')).toBe('/availability');
      expect(byId('generate')).toBeTruthy();
      expect(byId('no-provider')).toBeNull();
    });

    it('takes the hint about the training time away with the next try', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValueOnce({ kind: 'no_time' });
      await click('generate');
      stubs.planning.generate.mockResolvedValueOnce({ kind: 'rate_limited' });

      await click('generate');

      expect(byId('no-time')).toBeNull();
      expect(alerts()).toEqual([
        'Too many plans were requested. Please wait a minute and try again.',
      ]);
    });

    it('takes the hint about the training time away when another week is chosen', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'no_time' });
      await click('generate');

      await choose(LATER);

      expect(byId('no-time')).toBeNull();
      expect(alerts()).toEqual([]);
    });

    it('says when the coach gave nothing usable, and what was wrong', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({
        kind: 'not_usable',
        problems: [
          { path: '', message: 'The answer is not one JSON object.' },
          { path: 'workouts[0].sport', message: 'Must be one of the allowed values.' },
        ],
      });

      await click('generate');

      expect(alerts()).toEqual([
        'The coach did not give a plan that could be used. Please try again.',
      ]);
      const problems = Array.from(page.querySelectorAll('.problems li')).map(
        (li) => li.textContent,
      );
      expect(problems).toEqual([
        'The answer is not one JSON object.',
        'Must be one of the allowed values.',
      ]);
      expect(text()).toContain('Version 2');
    });

    it('drops the problems with the next try', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValueOnce({
        kind: 'not_usable',
        problems: [{ path: '', message: 'Bad.' }],
      });
      await click('generate');
      stubs.planning.generate.mockResolvedValueOnce({ kind: 'rate_limited' });

      await click('generate');

      expect(page.querySelector('.problems')).toBeNull();
    });

    it('shows the text of the server when the provider has a problem', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({
        kind: 'provider_problem',
        problem: 'invalid_key',
        message: 'The provider did not accept the key.',
        retry_after: null,
      });

      await click('generate');

      expect(alerts()).toEqual(['The provider did not accept the key.']);
    });

    it('says how long to wait if the provider said', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider is asking to slow down.',
        retry_after: 17,
      });

      await click('generate');

      expect(alerts()).toEqual(['The provider is asking to slow down. Try again in 17 seconds.']);
    });

    it('says when too many plans were requested', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'rate_limited' });

      await click('generate');

      expect(alerts()).toEqual([
        'Too many plans were requested. Please wait a minute and try again.',
      ]);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.planning.generate.mockResolvedValue({ kind: 'forbidden' });

      await click('generate');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows a general message when the call fails', async () => {
      await setup();
      stubs.planning.generate.mockRejectedValue(new Error('network'));

      await click('generate');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(button('generate').disabled).toBe(false);
    });
  });

  describe('confirming', () => {
    it('is not possible for a plan with errors, and says why', async () => {
      await setup();

      expect(button('confirm').disabled).toBe(true);
      expect(byId('cannot-confirm')?.textContent).toContain(
        'A plan with errors cannot be confirmed.',
      );
      await fixture.componentInstance['confirm']();
      expect(stubs.planning.confirm).not.toHaveBeenCalled();
    });

    it('is possible for a plan with only notes', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: WARNED } } });

      expect(button('confirm').disabled).toBe(false);
      expect(byId('cannot-confirm')).toBeNull();
    });

    it('confirms, shows the confirmed plan and refreshes the versions', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({
        kind: 'ok',
        plan: { ...VALID, status: 'confirmed', report: null, confirmed_at: '2026-11-14T08:00:00Z' },
        push: null,
      });

      await click('confirm');

      expect(stubs.planning.confirm).toHaveBeenCalledExactlyOnceWith(DRAFT_ID, false);
      expect(notice()).toBe('The plan is confirmed.');
      expect(byId('status')?.textContent?.trim()).toBe('Confirmed');
      expect(byId('confirm')).toBeNull();
      expect(byId('discard')).toBeNull();
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('says what it replaces', async () => {
      await setup({
        weeks: ok(weeks([version(), CONFIRMED_VERSION])),
        plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } },
      });

      expect(byId('replaces')?.textContent).toContain(
        'Confirming replaces version 1, which is confirmed now.',
      );
    });

    it('does not talk about replacing if nothing is confirmed', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });

      expect(byId('replaces')).toBeNull();
    });

    it('does one thing at a time', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      const pending = deferred<ConfirmPlanResult>();
      stubs.planning.confirm.mockReturnValue(pending.promise);

      button('confirm').click();
      await settle(fixture);
      await fixture.componentInstance['confirm']();

      expect(stubs.planning.confirm).toHaveBeenCalledTimes(1);
      expect(button('confirm').disabled).toBe(true);
      expect(button('discard').disabled).toBe(true);
      expect(button('generate').disabled).toBe(true);

      pending.resolve({ kind: 'forbidden' });
      await settle(fixture);
    });

    it('shows the errors the server found now', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({
        kind: 'not_confirmable',
        findings: [NO_FREE_DAY, MISMATCH],
      });

      await click('confirm');

      expect(alerts()).toEqual(['The plan has errors and cannot be confirmed.']);
      expect(page.querySelectorAll('.findings li')).toHaveLength(2);
      expect(button('confirm').disabled).toBe(true);
      expect(byId('status')?.textContent?.trim()).toBe('Draft');
    });

    it('reloads a plan that is no draft any more', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({ kind: 'not_a_draft' });
      stubs.planning.get.mockResolvedValue({ kind: 'ok', plan: CONFIRMED });

      await click('confirm');

      expect(alerts()).toEqual(['That plan is not a draft any more.']);
      expect(stubs.planning.get).toHaveBeenLastCalledWith(DRAFT_ID);
      expect(byId('status')?.textContent?.trim()).toBe('Confirmed');
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('says only that it is no draft if the plan is gone when it is reloaded', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({ kind: 'not_a_draft' });
      stubs.planning.get.mockResolvedValue({ kind: 'not_found' });

      await click('confirm');

      expect(alerts()).toEqual(['That plan is not a draft any more.']);
      expect(byId('status')).toBeNull();
    });

    it('drops a plan that does not exist any more', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({ kind: 'not_found' });

      await click('confirm');

      expect(alerts()).toEqual(['That plan does not exist any more.']);
      expect(byId('status')).toBeNull();
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('says when the session has ended', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockResolvedValue({ kind: 'forbidden' });

      await click('confirm');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows a general message when the call fails', async () => {
      await setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } });
      stubs.planning.confirm.mockRejectedValue(new Error('network'));

      await click('confirm');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(button('confirm').disabled).toBe(false);
    });

    it('is not offered for a plan that is decided on', async () => {
      await setup({ weeks: ok(weeks([CONFIRMED_VERSION])) });

      expect(byId('confirm')).toBeNull();
      await fixture.componentInstance['confirm']();
      expect(stubs.planning.confirm).not.toHaveBeenCalled();
    });
  });

  describe('sending to Intervals.icu', () => {
    const MIXED = sentPlan([SYNCED, FAILED, NOT_SENT]);
    const ALL_SYNCED = sentPlan([SYNCED, SYNCED, SYNCED]);
    const NOTHING = sentPlan([NOT_SENT, NOT_SENT, NOT_SENT]);
    const pushed = (plan: WeekPlan): PushPlanResult => ({
      kind: 'ok',
      plan,
      push: { ok: true, synced: 3, failed: 0, removed: 0, left_behind: 0 },
    });

    const open = (shown: WeekPlan) =>
      setup({
        weeks: ok(weeks([CONFIRMED_VERSION])),
        plans: { [CONFIRMED_ID]: { kind: 'ok', plan: shown } },
      });

    it('says where every workout stands and how the week stands', async () => {
      await open(MIXED);

      expect(byId('export-summary')?.textContent?.trim()).toBe(
        '1 of 3 workouts in Intervals.icu. 1 could not be sent. 1 not sent yet.',
      );
      const states = Array.from(page.querySelectorAll('[data-testid="export"]')).map((e) =>
        e.textContent?.trim(),
      );
      expect(states).toEqual([
        'In Intervals.icu',
        'Not sent: Intervals.icu did not accept this workout.',
        'Not sent to Intervals.icu yet',
      ]);
    });

    it('marks every state so that it can be styled', async () => {
      await open(MIXED);

      const marks = Array.from(page.querySelectorAll('[data-testid="export"]')).map((e) =>
        e.getAttribute('data-status'),
      );
      expect(marks).toEqual(['synced', 'failed', 'not_sent']);
    });

    it('offers to send a week that was not sent yet', async () => {
      await open(NOTHING);

      expect(byId('export-summary')?.textContent?.trim()).toBe('Not sent to Intervals.icu yet.');
      expect(button('send').textContent?.trim()).toBe('Send to Intervals.icu');
    });

    it('offers to send again once something was sent or failed', async () => {
      await open(MIXED);

      expect(button('send').textContent?.trim()).toBe('Send again');
    });

    it('warns about the events of an older version', async () => {
      await open(sentPlan([NOT_SENT, NOT_SENT, NOT_SENT], 3));

      expect(byId('export-summary')?.textContent).toContain(
        'Events of an older version are still in Intervals.icu; sending replaces them.',
      );
    });

    it('shows nothing about Intervals.icu for a plan that is not sent', async () => {
      await setup();

      expect(byId('export')).toBeNull();
      expect(byId('export-summary')).toBeNull();
      expect(byId('send')).toBeNull();
    });

    it('sends the plan, shows what came of it and the new state', async () => {
      await open(MIXED);
      stubs.planning.push.mockResolvedValue(pushed(ALL_SYNCED));

      await click('send');

      expect(stubs.planning.push).toHaveBeenCalledExactlyOnceWith(CONFIRMED_ID);
      expect(notice()).toBe('3 workouts were sent to Intervals.icu.');
      expect(byId('export-summary')?.textContent?.trim()).toBe('3 of 3 workouts in Intervals.icu.');
      expect(alerts()).toEqual([]);
    });

    it('tells what was removed and what failed', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({
        kind: 'ok',
        plan: MIXED,
        push: { ok: true, synced: 1, failed: 1, removed: 1, left_behind: 2 },
      });

      await click('send');

      expect(notice()).toBe(
        '1 workout was sent to Intervals.icu. 1 workout could not be sent. ' +
          '1 event of an older version removed. 2 events could not be removed yet.',
      );
    });

    it.each([
      ['not_connected', 'Intervals.icu is not connected. Connect it on the Connections page.'],
      ['invalid_key', 'Intervals.icu did not accept the stored API key. Connect it again.'],
    ] as const)('says how to go on if it is %s', async (problem, message) => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({ kind: 'problem', problem, message });

      await click('send');

      expect(alerts()).toEqual([message]);
      expect(byId('needs-connection')?.querySelector('a')?.getAttribute('href')).toBe(
        '/settings/connections',
      );
    });

    it('shows other problems without a way to connect', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({
        kind: 'problem',
        problem: 'unexpected',
        message: 'Intervals.icu answered in an unexpected way. Please try again later.',
      });

      await click('send');

      expect(alerts()).toEqual([
        'Intervals.icu answered in an unexpected way. Please try again later.',
      ]);
      expect(byId('needs-connection')).toBeNull();
    });

    it('clears the last problem when sending again', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValueOnce({
        kind: 'problem',
        problem: 'not_connected',
        message: 'Not connected.',
      });
      await click('send');
      stubs.planning.push.mockResolvedValue(pushed(ALL_SYNCED));

      await click('send');

      expect(alerts()).toEqual([]);
      expect(byId('needs-connection')).toBeNull();
    });

    it('says when the plan is gone', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({ kind: 'not_found' });

      await click('send');

      expect(alerts()).toEqual(['That plan does not exist any more.']);
      expect(byId('send')).toBeNull();
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('says when too much was sent in a short time', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({ kind: 'rate_limited' });

      await click('send');

      expect(alerts()).toEqual([
        'Too many sends in a short time. Please wait a minute and try again.',
      ]);
    });

    it('says when the session has ended', async () => {
      await open(NOTHING);
      stubs.planning.push.mockResolvedValue({ kind: 'forbidden' });

      await click('send');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when the call fails', async () => {
      await open(NOTHING);
      stubs.planning.push.mockRejectedValue(new Error('network'));

      await click('send');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(button('send').disabled).toBe(false);
    });

    it('waits for one thing at a time while it sends', async () => {
      await open(NOTHING);
      const pending = deferred<PushPlanResult>();
      stubs.planning.push.mockReturnValue(pending.promise);

      button('send').click();
      await settle(fixture);

      expect(byId('sending')?.textContent).toContain('Sending the week to Intervals.icu');
      expect(button('send').disabled).toBe(true);
      expect(select().disabled).toBe(true);
      await fixture.componentInstance['send']();
      expect(stubs.planning.push).toHaveBeenCalledTimes(1);

      pending.resolve(pushed(ALL_SYNCED));
      await settle(fixture);
      expect(byId('sending')).toBeNull();
      expect(button('send').disabled).toBe(false);
    });

    it('does nothing for a plan that is not confirmed', async () => {
      await setup();

      await fixture.componentInstance['send']();

      expect(stubs.planning.push).not.toHaveBeenCalled();
    });
  });

  describe('confirming and sending', () => {
    const confirmed = (push: PushOutcome | null): ConfirmPlanResult => ({
      kind: 'ok',
      plan: sentPlan([NOT_SENT, NOT_SENT, NOT_SENT]),
      push,
    });

    beforeEach(() => setup({ plans: { [DRAFT_ID]: { kind: 'ok', plan: VALID } } }));

    const checkbox = () => query<HTMLInputElement>(page, '[data-testid="send-after-confirm"]');

    it('does not send unless it is asked to', async () => {
      expect(checkbox().checked).toBe(false);
      stubs.planning.confirm.mockResolvedValue(confirmed(null));

      await click('confirm');

      expect(stubs.planning.confirm).toHaveBeenCalledExactlyOnceWith(DRAFT_ID, false);
      expect(notice()).toBe('The plan is confirmed.');
    });

    it('sends the week right after confirming it when asked to', async () => {
      checkbox().click();
      await settle(fixture);
      stubs.planning.confirm.mockResolvedValue(
        confirmed({ ok: true, synced: 3, failed: 0, removed: 0, left_behind: 0 }),
      );

      await click('confirm');

      expect(stubs.planning.confirm).toHaveBeenCalledExactlyOnceWith(DRAFT_ID, true);
      expect(notice()).toBe('The plan is confirmed. 3 workouts were sent to Intervals.icu.');
      expect(stubs.planning.push).not.toHaveBeenCalled();
    });

    it('keeps the plan confirmed when Intervals.icu is a problem, and says how to go on', async () => {
      checkbox().click();
      await settle(fixture);
      stubs.planning.confirm.mockResolvedValue(
        confirmed({
          ok: false,
          problem: 'not_connected',
          message: 'Intervals.icu is not connected. Connect it on the Connections page.',
        }),
      );

      await click('confirm');

      expect(notice()).toBe('The plan is confirmed.');
      expect(byId('status')?.textContent?.trim()).toBe('Confirmed');
      expect(alerts()).toEqual([
        'Intervals.icu is not connected. Connect it on the Connections page.',
      ]);
      expect(byId('needs-connection')).not.toBeNull();
      expect(byId('send')).not.toBeNull();
    });

    it('can not be changed while it waits', async () => {
      const pending = deferred<ConfirmPlanResult>();
      stubs.planning.confirm.mockReturnValue(pending.promise);

      button('confirm').click();
      await settle(fixture);

      expect(checkbox().disabled).toBe(true);
      pending.resolve(confirmed(null));
      await settle(fixture);
    });
  });

  describe('discarding', () => {
    it('discards a draft and shows it as discarded', async () => {
      await setup();
      stubs.planning.discard.mockResolvedValue({
        kind: 'ok',
        plan: { ...WITH_ERRORS, status: 'discarded', report: null },
      });

      await click('discard');

      expect(stubs.planning.discard).toHaveBeenCalledExactlyOnceWith(DRAFT_ID);
      expect(notice()).toBe('The draft was discarded.');
      expect(byId('status')?.textContent?.trim()).toBe('Discarded');
      expect(byId('discard')).toBeNull();
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
    });

    it('is not offered for a plan that is decided on, and does nothing if asked', async () => {
      await setup({ weeks: ok(weeks([CONFIRMED_VERSION])) });

      expect(byId('discard')).toBeNull();
      await fixture.componentInstance['discard']();
      expect(stubs.planning.discard).not.toHaveBeenCalled();
    });

    it('reloads a plan that is no draft any more', async () => {
      await setup();
      stubs.planning.discard.mockResolvedValue({ kind: 'not_a_draft' });
      stubs.planning.get.mockResolvedValue({ kind: 'ok', plan: CONFIRMED });

      await click('discard');

      expect(alerts()).toEqual(['That plan is not a draft any more.']);
      expect(byId('status')?.textContent?.trim()).toBe('Confirmed');
    });

    it('drops a plan that does not exist any more', async () => {
      await setup();
      stubs.planning.discard.mockResolvedValue({ kind: 'not_found' });

      await click('discard');

      expect(alerts()).toEqual(['That plan does not exist any more.']);
      expect(byId('status')).toBeNull();
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.planning.discard.mockResolvedValue({ kind: 'forbidden' });

      await click('discard');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('shows a general message when the call fails', async () => {
      await setup();
      stubs.planning.discard.mockRejectedValue(new Error('network'));

      await click('discard');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(button('discard').disabled).toBe(false);
    });
  });

  describe('opening a plan that fails', () => {
    it('says that it is gone and refreshes the versions', async () => {
      await setup({ plans: {} });

      expect(alerts()).toEqual(['That plan does not exist any more.']);
      expect(stubs.planning.weeks).toHaveBeenCalledTimes(2);
      expect(byId('status')).toBeNull();
    });

    it('shows a general message when the call fails', async () => {
      await setup();
      stubs.planning.get.mockRejectedValue(new Error('network'));

      await click('version-1');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('says when the session has ended', async () => {
      await setup();
      stubs.planning.get.mockResolvedValue({ kind: 'forbidden' });

      await click('version-1');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('does not open a second plan while one is opening', async () => {
      await setup();
      const pending = deferred<GetPlanResult>();
      stubs.planning.get.mockReturnValue(pending.promise);
      stubs.planning.get.mockClear();

      const first = fixture.componentInstance['open'](OLD_ID);
      await fixture.componentInstance['open'](DRAFT_ID);

      expect(stubs.planning.get).toHaveBeenCalledTimes(1);
      pending.resolve({ kind: 'not_found' });
      await first;
    });
  });

  describe('changing a plan by hand', () => {
    const NEW_ID = '01a1d73d-0000-7000-8000-0000000000aa';
    const editor = () => page.querySelector('app-plan-editor');

    /** The draft the server stores for a change: version 3, with its checks. */
    function changed(report: WeekPlan['report'] = { valid: true, findings: [] }): WeekPlan {
      return plan({ id: NEW_ID, version: 3, parent: DRAFT_ID, report });
    }

    async function open() {
      await click('change-plan');
    }

    describe('offering it', () => {
      it('is offered on a draft', async () => {
        await setup();

        expect(byId('change-plan')).toBeTruthy();
        expect(byId('change-plan')?.textContent?.trim()).toBe('Change this plan');
      });

      it('is offered on a confirmed plan', async () => {
        await setup({ weeks: ok(weeks([CONFIRMED_VERSION])) });

        expect(byId('status')?.textContent).toBe('Confirmed');
        expect(byId('change-plan')).toBeTruthy();
      });

      it('is not offered on a version that was discarded or replaced', async () => {
        await setup();

        await click('version-1'); // discarded

        expect(byId('status')?.textContent).toBe('Discarded');
        expect(byId('change-plan')).toBeNull();
      });

      it('is not offered when there is no plan', async () => {
        await setup({ weeks: ok(weeks([OLD])) });

        expect(byId('change-plan')).toBeNull();
      });

      it('is switched off while something else runs', async () => {
        await setup();
        const pending = deferred<DiscardPlanResult>();
        stubs.planning.discard.mockReturnValue(pending.promise);

        button('discard').click();
        await fixture.whenStable();

        expect(button('change-plan').disabled).toBe(true);
        pending.resolve({ kind: 'ok', plan: plan({ status: 'discarded', report: null }) });
        await settle(fixture);
      });
    });

    describe('while it is changed', () => {
      it('shows the editor in the place of the plan and checks the plan as it is', async () => {
        await setup();

        await open();

        expect(editor()).toBeTruthy();
        expect(page.querySelector('article.plan')).toBeNull();
        expect(page.querySelector('app-plan-editor h2')?.textContent).toBe('Changing version 2');
        expect(stubs.planning.check).toHaveBeenCalledTimes(1);
        expect(stubs.planning.check.mock.calls[0][0]).toBe(NEXT);
      });

      it('drops the messages of before', async () => {
        await setup();
        stubs.planning.generate.mockResolvedValue({ kind: 'rate_limited' });
        await click('generate');
        expect(alerts().length).toBeGreaterThan(0);

        await open();

        expect(alerts()).toEqual([]);
      });

      it('allows nothing else to start', async () => {
        await setup();
        await open();

        expect(select().disabled).toBe(true);
        expect(button('generate').disabled).toBe(true);
        expect(page.querySelector<HTMLButtonElement>('[data-testid="version-1"]')?.disabled).toBe(
          true,
        );
        expect(byId('confirm')).toBeNull();
        expect(byId('discard')).toBeNull();
      });

      it('lets no other action in even when it is called', async () => {
        await setup();
        await open();
        stubs.planning.get.mockClear();

        await fixture.componentInstance['selectWeek'](LATER);
        await fixture.componentInstance['generate']();
        await fixture.componentInstance['confirm']();
        await fixture.componentInstance['discard']();
        await fixture.componentInstance['send']();
        await fixture.componentInstance['open'](OLD_ID);

        expect(stubs.planning.generate).not.toHaveBeenCalled();
        expect(stubs.planning.confirm).not.toHaveBeenCalled();
        expect(stubs.planning.discard).not.toHaveBeenCalled();
        expect(stubs.planning.push).not.toHaveBeenCalled();
        expect(stubs.planning.get).not.toHaveBeenCalled();
        expect(select().value).toBe(NEXT);
      });

      it('does not open a second editor', async () => {
        await setup();
        await open();

        fixture.componentInstance['startChanging']();
        await settle(fixture);

        expect(page.querySelectorAll('app-plan-editor')).toHaveLength(1);
        expect(stubs.planning.check).toHaveBeenCalledTimes(1);
      });

      it('sends nothing to be stored before the changes are saved', async () => {
        await setup();
        await open();
        await click('remove-0');

        expect(stubs.planning.revise).not.toHaveBeenCalled();
      });
    });

    describe('dropping the changes', () => {
      it('brings back the plan as it was and stores nothing', async () => {
        await setup();
        await open();
        await click('remove-0');

        await click('discard-changes');

        expect(editor()).toBeNull();
        expect(byId('status')?.textContent).toBe('Draft');
        expect(page.querySelectorAll('[data-testid^="workout-"]').length).toBe(3);
        expect(stubs.planning.revise).not.toHaveBeenCalled();
        expect(select().disabled).toBe(false);
        expect(button('generate').disabled).toBe(false);
      });

      it('offers to change it again, from the plan as it was', async () => {
        await setup();
        await open();
        await click('remove-0');
        await click('discard-changes');

        await open();

        expect(
          page.querySelectorAll('app-plan-editor [data-testid^="editor-workout-"]'),
        ).toHaveLength(3);
      });
    });

    describe('saving the changes', () => {
      it('shows the new draft with its checks, says so and fetches the versions again', async () => {
        await setup();
        await open();
        await click('remove-0');
        stubs.planning.revise.mockResolvedValue({ kind: 'ok', plan: changed() });
        stubs.planning.weeks.mockClear();

        await click('save-version');

        expect(stubs.planning.revise).toHaveBeenCalledTimes(1);
        expect(stubs.planning.revise.mock.calls[0][0]).toBe(DRAFT_ID);
        expect(editor()).toBeNull();
        expect(page.querySelector('.plan h2')?.textContent).toBe('Version 3');
        expect(byId('status')?.textContent).toBe('Draft');
        expect(notice()).toBe(
          'Your changes were saved as version 3. Read it, then confirm it to make it the plan of the week.',
        );
        expect(stubs.planning.weeks).toHaveBeenCalledTimes(1);
        expect(select().disabled).toBe(false);
      });

      it('says that a draft with errors cannot be confirmed yet', async () => {
        await setup();
        await open();
        await click('remove-0');
        stubs.planning.revise.mockResolvedValue({
          kind: 'ok',
          plan: changed({ valid: false, findings: [MISMATCH] }),
        });

        await click('save-version');

        expect(notice()).toBe(
          'Your changes were saved as version 3. It has errors and cannot be confirmed yet.',
        );
        expect(button('confirm').disabled).toBe(true);
      });

      it('can be confirmed like any draft', async () => {
        await setup();
        await open();
        await click('remove-0');
        stubs.planning.revise.mockResolvedValue({ kind: 'ok', plan: changed() });
        await click('save-version');
        stubs.planning.confirm.mockResolvedValue({
          kind: 'ok',
          plan: plan({ id: NEW_ID, version: 3, status: 'confirmed', report: null }),
          push: null,
        });

        await click('confirm');

        expect(stubs.planning.confirm).toHaveBeenCalledExactlyOnceWith(NEW_ID, false);
      });

      it('keeps the editor and the changes when the server refuses', async () => {
        await setup();
        await open();
        await click('remove-0');
        stubs.planning.revise.mockResolvedValue({ kind: 'not_revisable' });

        await click('save-version');

        expect(editor()).toBeTruthy();
        expect(
          page.querySelectorAll('app-plan-editor [data-testid^="editor-workout-"]'),
        ).toHaveLength(2);
        expect(byId('editor-message')?.textContent).toContain('cannot be changed any more');
      });

      it('says when the session has ended', async () => {
        await setup();
        await open();
        await click('remove-0');
        stubs.planning.revise.mockResolvedValue({ kind: 'forbidden' });

        await click('save-version');

        expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
        expect(editor()).toBeNull();
      });

      it('says when the session ends during a check', async () => {
        await setup();
        stubs.planning.check.mockResolvedValue({ kind: 'forbidden' });

        await open();

        expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      });
    });
  });

  describe('restoring a version', () => {
    const NEW_ID = '01a1d73d-0000-7000-8000-0000000000bb';
    const REPLACED_ID = '01a1d73d-0000-7000-8000-0000000000cc';
    const REPLACED = plan({
      id: REPLACED_ID,
      version: 1,
      status: 'superseded',
      confirmed_at: '2026-11-13T23:28:07.353166Z',
      report: null,
    });
    const REPLACED_VERSION = version({
      id: REPLACED_ID,
      version: 1,
      status: 'superseded',
      confirmed_at: '2026-11-13T23:28:07.353166Z',
    });

    /** The draft the server makes of a version: version 4, checked as of today. */
    function restored(report: WeekPlan['report'] = { valid: true, findings: [] }): WeekPlan {
      return plan({ id: NEW_ID, version: 4, parent: OLD_ID, report });
    }

    async function openDiscarded() {
      await setup();
      await click('version-1'); // the discarded one
    }

    describe('offering it', () => {
      it('is offered on a version that was discarded', async () => {
        await openDiscarded();

        expect(byId('status')?.textContent).toBe('Discarded');
        expect(byId('restore')?.textContent?.trim()).toBe('Make this the new draft');
        expect(byId('restore-hint')?.textContent).toContain('Restoring copies it as a new draft');
      });

      it('is offered on a version that was replaced', async () => {
        await setup({
          weeks: ok(weeks([version(), REPLACED_VERSION])),
          plans: {
            [DRAFT_ID]: { kind: 'ok', plan: WITH_ERRORS },
            [REPLACED_ID]: { kind: 'ok', plan: REPLACED },
          },
        });

        await click('version-1');

        expect(byId('status')?.textContent).toBe('Replaced');
        expect(byId('restore')).toBeTruthy();
      });

      it('is not offered on a draft', async () => {
        await setup();

        expect(byId('status')?.textContent).toBe('Draft');
        expect(byId('restore')).toBeNull();
        expect(byId('restore-hint')).toBeNull();
      });

      it('is not offered on a confirmed plan', async () => {
        await setup({ weeks: ok(weeks([CONFIRMED_VERSION])) });

        expect(byId('status')?.textContent).toBe('Confirmed');
        expect(byId('restore')).toBeNull();
      });

      it('is switched off while something else runs', async () => {
        await openDiscarded();
        const pending = deferred<GetPlanResult>();
        stubs.planning.get.mockReturnValue(pending.promise);

        button('version-2').click();
        await fixture.whenStable();

        expect(button('restore').disabled).toBe(true);
        pending.resolve({ kind: 'ok', plan: WITH_ERRORS });
        await settle(fixture);
      });
    });

    describe('doing it', () => {
      it('shows the new draft with its checks and says so', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({ kind: 'ok', plan: restored() });
        stubs.planning.weeks.mockClear();

        await click('restore');

        expect(stubs.planning.restore).toHaveBeenCalledExactlyOnceWith(OLD_ID);
        expect(page.querySelector('.plan h2')?.textContent).toBe('Version 4');
        expect(byId('status')?.textContent).toBe('Draft');
        expect(notice()).toBe(
          'Version 1 was restored as a new draft (version 4). Read it, then confirm it to make it the plan of the week.',
        );
        expect(stubs.planning.weeks).toHaveBeenCalledTimes(1);
        expect(byId('restore')).toBeNull();
        expect(byId('change-plan')).toBeTruthy();
      });

      it('says when it has errors with what the user can do today', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({
          kind: 'ok',
          plan: restored({ valid: false, findings: [MISMATCH] }),
        });

        await click('restore');

        expect(notice()).toBe(
          'Version 1 was restored as a new draft (version 4). With what you can do today it has errors and cannot be confirmed yet.',
        );
        expect(button('confirm').disabled).toBe(true);
      });

      it('says that it works while it works, and allows one thing at a time', async () => {
        await openDiscarded();
        const pending = deferred<RestorePlanResult>();
        stubs.planning.restore.mockReturnValue(pending.promise);

        button('restore').click();
        await fixture.whenStable();

        expect(byId('restoring')).toBeTruthy();
        expect(button('restore').disabled).toBe(true);
        expect(select().disabled).toBe(true);
        await fixture.componentInstance['restore']();
        expect(stubs.planning.restore).toHaveBeenCalledTimes(1);
        pending.resolve({ kind: 'ok', plan: restored() });
        await settle(fixture);
        expect(byId('restoring')).toBeNull();
      });
    });

    describe('when it does not work', () => {
      it('says when the week cannot be planned any more, and keeps the version on the screen', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({ kind: 'not_plannable' });

        await click('restore');

        expect(alerts()).toEqual([
          'This week cannot be planned any more, so a version of it cannot be restored.',
        ]);
        expect(byId('status')?.textContent).toBe('Discarded');
        expect(button('restore').disabled).toBe(false);
      });

      it('shows the version as it is now when it was decided on meanwhile', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({ kind: 'not_restorable' });
        stubs.planning.get.mockClear();
        stubs.planning.weeks.mockClear();

        await click('restore');

        expect(alerts()).toEqual([
          'Only a version that was replaced or discarded can be restored.',
        ]);
        expect(stubs.planning.get).toHaveBeenCalledWith(OLD_ID);
        expect(stubs.planning.weeks).toHaveBeenCalledTimes(1);
      });

      it('says when the version is gone, and fetches the versions again', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({ kind: 'not_found' });
        stubs.planning.weeks.mockClear();

        await click('restore');

        expect(alerts()).toEqual(['That plan does not exist any more.']);
        expect(byId('status')).toBeNull();
        expect(stubs.planning.weeks).toHaveBeenCalledTimes(1);
      });

      it('says when the session has ended', async () => {
        await openDiscarded();
        stubs.planning.restore.mockResolvedValue({ kind: 'forbidden' });

        await click('restore');

        expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      });

      it('says so when the request fails, and can be tried again', async () => {
        await openDiscarded();
        stubs.planning.restore.mockRejectedValueOnce(new Error('down'));

        await click('restore');

        expect(alerts()).toEqual(['Something went wrong. Please try again.']);
        expect(button('restore').disabled).toBe(false);
        stubs.planning.restore.mockResolvedValue({ kind: 'ok', plan: restored() });
        await click('restore');
        expect(stubs.planning.restore).toHaveBeenCalledTimes(2);
      });

      it('lets nothing in while the editor is open', async () => {
        await setup();
        await click('change-plan');

        await fixture.componentInstance['restore']();

        expect(stubs.planning.restore).not.toHaveBeenCalled();
      });
    });
  });
});
