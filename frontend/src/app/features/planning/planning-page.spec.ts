import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import { PlanningApi } from '../../core/planning/planning-api';
import {
  ConfirmPlanResult,
  DiscardPlanResult,
  Finding,
  GenerateResult,
  GetPlanResult,
  ListWeeksResult,
  PlanVersion,
  PlannableWeek,
  WeekPlan,
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
        segments: [],
      },
      {
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
        segments: [],
      },
      {
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
        segments: [
          { kind: 'warmup', seconds: 900, repeat: 1, zone_system: 'pace', zone: 2 },
          { kind: 'work', seconds: 600, repeat: 3, zone_system: 'pace', zone: 4 },
        ],
      },
    ],
    report: { valid: false, findings: [MISMATCH] },
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
      confirm: vi.fn<(id: string) => Promise<ConfirmPlanResult>>(),
      discard: vi.fn<(id: string) => Promise<DiscardPlanResult>>(),
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
      });

      await click('confirm');

      expect(stubs.planning.confirm).toHaveBeenCalledExactlyOnceWith(DRAFT_ID);
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
});
