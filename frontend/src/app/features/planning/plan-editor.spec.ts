import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PlanningApi } from '../../core/planning/planning-api';
import {
  CheckPlanResult,
  EditedPlan,
  Finding,
  RevisePlanResult,
  WeekPlan,
  Workout,
} from '../../core/planning/planning-models';
import { query, settle } from '../../testing/dom';
import { PlanEditor } from './plan-editor';

const WEEK = '2026-11-16';
const RIDE_LINEAGE = '01a1d73d-aaaa-7000-8000-000000000001';
const RUN_LINEAGE = '01a1d73d-aaaa-7000-8000-000000000002';
const INTERVALS_LINEAGE = '01a1d73d-aaaa-7000-8000-000000000003';
const PLAN_ID = '01a1d73d-2f26-7356-907e-f1475fc2aeab';

function workout(changes: Partial<Workout>): Workout {
  return {
    lineage: RIDE_LINEAGE,
    day: '2026-11-16',
    sport: 'cycling',
    title: 'Endurance ride',
    goal: 'endurance',
    duration_minutes: 60,
    zone_system: 'power',
    zone: 2,
    target: null,
    export: null,
    notes: '',
    slot: 'morning',
    stretching_minutes: 0,
    exercises: [],
    segments: [],
    ...changes,
  };
}

function plan(changes: Partial<WeekPlan> = {}): WeekPlan {
  return {
    id: PLAN_ID,
    week_start: WEEK,
    version: 2,
    status: 'confirmed',
    reason: 'Drafted by the coach',
    rationale: 'Base week.',
    parent: null,
    created_at: '2026-11-13T23:27:53.638352Z',
    confirmed_at: '2026-11-13T23:28:07.353166Z',
    workouts: [
      workout({}),
      workout({
        lineage: RUN_LINEAGE,
        day: '2026-11-18',
        sport: 'running',
        title: 'Easy run',
        duration_minutes: 45,
        zone_system: null,
        zone: null,
        slot: null,
        notes: 'Keep it easy',
      }),
      workout({
        lineage: INTERVALS_LINEAGE,
        day: '2026-11-20',
        sport: 'running',
        title: 'Intervals',
        goal: 'threshold',
        duration_minutes: 70,
        zone_system: null,
        zone: null,
        slot: null,
        segments: [
          {
            kind: 'warmup',
            seconds: 900,
            repeat: 1,
            zone_system: 'pace',
            zone: 2,
            target: null,
          },
        ],
      }),
    ],
    report: null,
    export: { synced: 3, failed: 0, not_sent: 0, older: 0 },
    ...changes,
  };
}

const ERROR: Finding = {
  severity: 'error',
  code: 'day_over_capacity',
  message: 'Too long for this day.',
  path: 'workouts[1]',
};
const NOTE: Finding = {
  severity: 'warning',
  code: 'no_free_day',
  message: 'The week has no day without a workout.',
  path: '',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const identity = (sent: EditedPlan): CheckPlanResult => ({
  kind: 'ok',
  report: { valid: true, findings: [] },
  order: sent.workouts.map((_, index) => index),
});

describe('PlanEditor', () => {
  let check: ReturnType<typeof vi.fn<(week: string, plan: EditedPlan) => Promise<CheckPlanResult>>>;
  let revise: ReturnType<typeof vi.fn<(id: string, plan: EditedPlan) => Promise<RevisePlanResult>>>;
  let fixture: ComponentFixture<PlanEditor>;
  let page: HTMLElement;
  const saved = vi.fn();
  const cancelled = vi.fn();
  const signedOut = vi.fn();

  async function setup(shown: WeekPlan = plan()) {
    check = vi.fn<(week: string, plan: EditedPlan) => Promise<CheckPlanResult>>();
    check.mockImplementation(async (_week, sent) => identity(sent));
    revise = vi.fn<(id: string, plan: EditedPlan) => Promise<RevisePlanResult>>();
    for (const spy of [saved, cancelled, signedOut]) {
      spy.mockClear();
    }
    TestBed.configureTestingModule({
      imports: [PlanEditor],
      providers: [{ provide: PlanningApi, useValue: { check, revise } }],
    });
    fixture = TestBed.createComponent(PlanEditor);
    fixture.componentRef.setInput('plan', shown);
    fixture.componentInstance.saved.subscribe(saved);
    fixture.componentInstance.cancelled.subscribe(cancelled);
    fixture.componentInstance.signedOut.subscribe(signedOut);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const byId = (id: string) => page.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const button = (id: string) => query<HTMLButtonElement>(page, `[data-testid="${id}"]`);
  const titles = () => Array.from(page.querySelectorAll('h4')).map((h) => h.textContent?.trim());
  const days = () => Array.from(page.querySelectorAll('h3')).map((h) => h.textContent?.trim());
  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ');

  async function click(id: string) {
    button(id).click();
    await settle(fixture);
  }

  function choose(id: string, value: string) {
    const element = query<HTMLSelectElement>(page, `#${id}`);
    element.value = value;
    element.dispatchEvent(new Event('change'));
  }

  function type(id: string, value: string) {
    const element = query<HTMLInputElement | HTMLTextAreaElement>(page, `#${id}`);
    element.value = value;
    element.dispatchEvent(new Event('input'));
  }

  /** The last plan that was sent to be checked. */
  function lastChecked(): EditedPlan {
    return check.mock.calls[check.mock.calls.length - 1][1];
  }

  describe('the plan as it is', () => {
    it('shows the version and the workouts by day', async () => {
      await setup();

      expect(page.querySelector('h2')?.textContent).toBe('Changing version 2');
      expect(days()).toEqual(['Mon 16 Nov', 'Wed 18 Nov', 'Fri 20 Nov']);
      expect(titles()).toEqual(['Endurance ride', 'Easy run', 'Intervals']);
      expect(text()).toContain('Morning');
      expect(text()).toContain('Power zone 2');
      expect(text()).toContain('Interval structure with 1 part');
    });

    it('shows the notes of a workout as text', async () => {
      await setup(plan({ workouts: [workout({ notes: '<b>Easy</b> now' })] }));

      expect(text()).toContain('<b>Easy</b> now');
      expect(page.querySelector('.notes b')).toBeNull();
    });

    it('checks it as it is first, with the lineages and without what the server knows', async () => {
      await setup();

      expect(check).toHaveBeenCalledTimes(1);
      const [week, sent] = check.mock.calls[0];
      expect(week).toBe(WEEK);
      expect(sent.rationale).toBe('Base week.');
      expect(sent.workouts.map((w) => w.lineage)).toEqual([
        RIDE_LINEAGE,
        RUN_LINEAGE,
        INTERVALS_LINEAGE,
      ]);
      expect(JSON.stringify(sent)).not.toContain('target');
      expect(JSON.stringify(sent)).not.toContain('export');
    });

    it('says that nothing is to be pointed out', async () => {
      await setup();

      expect(byId('editor-all-clear')).toBeTruthy();
      expect(byId('editor-checking')).toBeNull();
    });

    it('works for a draft too', async () => {
      await setup(
        plan({
          status: 'draft',
          confirmed_at: null,
          export: null,
          report: { valid: true, findings: [] },
        }),
      );

      expect(titles()).toHaveLength(3);
      expect(check).toHaveBeenCalledTimes(1);
    });

    it('sends nothing but checks until it is saved', async () => {
      await setup();

      expect(revise).not.toHaveBeenCalled();
    });
  });

  describe('what the checks say', () => {
    it('shows the findings at the workout they name, through the order of the answer', async () => {
      await setup();
      // The server numbers the workouts as stored: its workout 1 is the first one that was sent.
      check.mockResolvedValue({
        kind: 'ok',
        report: { valid: false, findings: [ERROR] },
        order: [2, 0, 1],
      });

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-findings-0')?.textContent).toContain('Too long for this day.');
      expect(byId('editor-findings-1')).toBeNull();
      expect(byId('editor-findings-2')).toBeNull();
    });

    it('shows the findings of the week above the workouts', async () => {
      await setup();
      check.mockResolvedValue({
        kind: 'ok',
        report: { valid: true, findings: [NOTE] },
        order: [0, 1, 2],
      });

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-week')?.textContent).toContain('The week has no day without a workout.');
      expect(byId('editor-findings-0')).toBeNull();
    });

    it('counts the errors and the notes, and says that a plan with errors cannot be confirmed', async () => {
      await setup();
      check.mockResolvedValue({
        kind: 'ok',
        report: { valid: false, findings: [ERROR, NOTE] },
        order: [0, 1, 2],
      });

      await fixture.componentInstance['check']();
      await settle(fixture);

      const summary = byId('editor-summary')?.textContent?.replace(/\s+/g, ' ');
      expect(summary).toContain('1 error and 1 note');
      expect(summary).toContain('can be saved, but it cannot be confirmed');
    });

    it('does not mention the confirming when there are only notes', async () => {
      await setup();
      check.mockResolvedValue({
        kind: 'ok',
        report: { valid: true, findings: [NOTE] },
        order: [0, 1, 2],
      });

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-summary')?.textContent).toContain('0 errors and 1 note');
      expect(byId('editor-summary')?.textContent).not.toContain('cannot be confirmed');
    });

    it('says that it checks, and shows no finding meanwhile', async () => {
      await setup();
      const pending = deferred<CheckPlanResult>();
      check.mockReturnValue(pending.promise);

      await click('remove-0');

      expect(byId('editor-checking')?.textContent).toContain('Checking');
      expect(byId('editor-all-clear')).toBeNull();
      pending.resolve(identity(lastChecked()));
      await settle(fixture);
      expect(byId('editor-checking')).toBeNull();
    });

    it('drops an answer that comes after a newer change', async () => {
      await setup();
      const first = deferred<CheckPlanResult>();
      const second = deferred<CheckPlanResult>();
      check.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

      await click('remove-0');
      await click('remove-0');
      second.resolve({ kind: 'ok', report: { valid: true, findings: [NOTE] }, order: [0] });
      await settle(fixture);
      // The answer of the first check comes late and says something else.
      first.resolve({ kind: 'ok', report: { valid: false, findings: [ERROR] }, order: [0, 1] });
      await settle(fixture);

      expect(byId('editor-week')?.textContent).toContain('The week has no day');
      expect(byId('editor-summary')?.textContent).toContain('0 errors and 1 note');
      expect(byId('editor-findings-0')).toBeNull();
      expect(byId('editor-checking')).toBeNull();
    });

    it('does not stop saying "checking" because an older answer came in', async () => {
      await setup();
      const first = deferred<CheckPlanResult>();
      const second = deferred<CheckPlanResult>();
      check.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
      await click('remove-0');
      await click('remove-0');

      first.resolve(identity(lastChecked()));
      await settle(fixture);

      expect(byId('editor-checking')).toBeTruthy();
      second.resolve(identity(lastChecked()));
      await settle(fixture);
      expect(byId('editor-checking')).toBeNull();
    });

    it.each([
      [
        'the week cannot be planned',
        { kind: 'not_plannable' } as CheckPlanResult,
        'cannot be planned any more',
      ],
      [
        'the plan cannot be read',
        {
          kind: 'invalid',
          problems: [{ path: 'workouts[0].title', message: 'Must not be empty.' }],
        } as CheckPlanResult,
        'The plan cannot be read:',
      ],
    ])('says when %s', async (_name, result, expected) => {
      await setup();
      check.mockResolvedValue(result);

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-message')?.textContent).toContain(expected);
    });

    it('lists what was wrong with the plan', async () => {
      await setup();
      check.mockResolvedValue({
        kind: 'invalid',
        problems: [{ path: 'workouts[0].title', message: 'Must not be empty.' }],
      });

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-problems')?.textContent).toContain('Must not be empty.');
    });

    it('tells the page when the session has ended', async () => {
      await setup();
      check.mockResolvedValue({ kind: 'forbidden' });

      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(signedOut).toHaveBeenCalledTimes(1);
    });

    it('says so when the check fails, and shows no findings of an earlier one', async () => {
      await setup();
      check.mockResolvedValueOnce({
        kind: 'ok',
        report: { valid: false, findings: [NOTE] },
        order: [0, 1, 2],
      });
      await fixture.componentInstance['check']();
      await settle(fixture);
      expect(byId('editor-week')).toBeTruthy();

      check.mockRejectedValue(new Error('down'));
      await fixture.componentInstance['check']();
      await settle(fixture);

      expect(byId('editor-message')?.textContent).toContain('The checks could not be run');
      expect(byId('editor-week')).toBeNull();
      expect(byId('editor-checking')).toBeNull();
    });
  });

  describe('changing a workout', () => {
    it('opens the form with the workout', async () => {
      await setup();

      await click('change-1');

      expect(query<HTMLInputElement>(page, '#workout-title').value).toBe('Easy run');
      expect(byId('editor-workout-1')).toBeNull(); // the form takes its place
      expect(byId('editor-workout-0')).toBeTruthy();
    });

    it('shows the change and checks the plan again', async () => {
      await setup();
      await click('change-1');

      type('workout-title', 'Long run');
      type('workout-duration', '90');
      await click('workout-save');

      expect(titles()).toContain('Long run');
      expect(titles()).not.toContain('Easy run');
      expect(check).toHaveBeenCalledTimes(2);
      const sent = lastChecked().workouts[1];
      expect(sent).toMatchObject({ title: 'Long run', duration_minutes: 90, lineage: RUN_LINEAGE });
      expect(page.querySelector('app-workout-form')).toBeNull();
    });

    it('moves a workout to another day', async () => {
      await setup();
      await click('change-1');

      choose('workout-day', '2026-11-21');
      choose('workout-slot', 'evening');
      await click('workout-save');

      expect(days()).toEqual(['Mon 16 Nov', 'Fri 20 Nov', 'Sat 21 Nov']);
      expect(lastChecked().workouts[1]).toMatchObject({
        day: '2026-11-21',
        slot: 'evening',
        lineage: RUN_LINEAGE,
      });
    });

    it('shows the workouts of a day in the order of the times of day', async () => {
      await setup();
      await click('change-1');
      choose('workout-day', '2026-11-16');
      choose('workout-slot', 'evening');
      await click('workout-save');

      expect(days()).toEqual(['Mon 16 Nov', 'Fri 20 Nov']);
      expect(titles()).toEqual(['Endurance ride', 'Easy run', 'Intervals']);

      await click('change-1');
      choose('workout-slot', 'morning');
      type('workout-title', 'Early run');
      await click('workout-save');

      // the ride was first in the list, so it stays first among two mornings
      expect(titles()).toEqual(['Endurance ride', 'Early run', 'Intervals']);
    });

    it('leaves everything as it was when the form is cancelled', async () => {
      await setup();
      await click('change-1');
      type('workout-title', 'Typed');

      await click('workout-cancel');

      expect(titles()).toEqual(['Endurance ride', 'Easy run', 'Intervals']);
      expect(check).toHaveBeenCalledTimes(1);
      expect(button('save-version').disabled).toBe(true);
    });

    it('keeps the interval structure of a workout that is changed', async () => {
      await setup();
      await click('change-2');

      choose('workout-day', '2026-11-19');
      await click('workout-save');

      expect(lastChecked().workouts[2].segments).toHaveLength(1);
      expect(lastChecked().workouts[2].day).toBe('2026-11-19');
    });
  });

  describe('removing and adding', () => {
    it('removes a workout and checks the plan again', async () => {
      await setup();

      await click('remove-1');

      expect(titles()).toEqual(['Endurance ride', 'Intervals']);
      expect(lastChecked().workouts.map((w) => w.lineage)).toEqual([
        RIDE_LINEAGE,
        INTERVALS_LINEAGE,
      ]);
      expect(check).toHaveBeenCalledTimes(2);
    });

    it('can remove everything', async () => {
      await setup();

      await click('remove-0');
      await click('remove-0');
      await click('remove-0');

      expect(byId('editor-empty')).toBeTruthy();
      expect(lastChecked().workouts).toEqual([]);
    });

    it('adds a new workout without a lineage', async () => {
      await setup();

      await click('add-workout');
      expect(page.querySelector('h3#workout-form-title')?.textContent).toBe('Add a workout');
      type('workout-title', 'Swim');
      choose('workout-sport', 'swimming');
      choose('workout-day', '2026-11-22');
      await click('workout-save');

      expect(titles()).toContain('Swim');
      expect(lastChecked().workouts).toHaveLength(4);
      expect(lastChecked().workouts[3]).toMatchObject({
        lineage: null,
        title: 'Swim',
        sport: 'swimming',
        day: '2026-11-22',
      });
      expect(days()).toContain('Sun 22 Nov');
    });

    it('does not add anything when the form is cancelled', async () => {
      await setup();
      await click('add-workout');

      await click('workout-cancel');

      expect(titles()).toHaveLength(3);
      expect(page.querySelector('app-workout-form')).toBeNull();
      expect(byId('add-workout')).toBeTruthy();
    });

    it('allows one form at a time', async () => {
      await setup();
      await click('change-0');

      expect(button('change-1').disabled).toBe(true);
      expect(button('remove-1').disabled).toBe(true);
      expect(button('add-workout').disabled).toBe(true);
      expect(button('save-version').disabled).toBe(true);
      expect(page.querySelectorAll('app-workout-form')).toHaveLength(1);
    });
  });

  describe('saving', () => {
    const NEW_DRAFT = plan({
      id: '01a1d73d-0000-7000-8000-000000000009',
      status: 'draft',
      version: 3,
    });

    it('cannot be done before something is changed', async () => {
      await setup();

      expect(button('save-version').disabled).toBe(true);
    });

    it('cannot be done once a change is taken back', async () => {
      await setup();
      await click('change-1');
      type('workout-title', 'Other');
      await click('workout-save');
      expect(button('save-version').disabled).toBe(false);

      await click('change-1');
      type('workout-title', 'Easy run');
      await click('workout-save');

      expect(button('save-version').disabled).toBe(true);
    });

    it('stores the plan as a new version of the plan it started from and hands it on', async () => {
      await setup();
      await click('remove-2');
      revise.mockResolvedValue({ kind: 'ok', plan: NEW_DRAFT });

      await click('save-version');

      expect(revise).toHaveBeenCalledTimes(1);
      const [id, sent] = revise.mock.calls[0];
      expect(id).toBe(PLAN_ID);
      expect(sent).toEqual({
        week_start: WEEK,
        rationale: 'Base week.',
        workouts: lastChecked().workouts,
      });
      expect(saved).toHaveBeenCalledExactlyOnceWith(NEW_DRAFT);
    });

    it('can be done with errors in the plan', async () => {
      await setup();
      check.mockResolvedValue({
        kind: 'ok',
        report: { valid: false, findings: [ERROR] },
        order: [0, 1],
      });
      await click('remove-0');
      revise.mockResolvedValue({ kind: 'ok', plan: NEW_DRAFT });

      expect(button('save-version').disabled).toBe(false);
      await click('save-version');

      expect(saved).toHaveBeenCalledTimes(1);
    });

    it('switches everything off while it saves, and says so', async () => {
      await setup();
      await click('remove-2');
      const pending = deferred<RevisePlanResult>();
      revise.mockReturnValue(pending.promise);

      button('save-version').click();
      await fixture.whenStable();

      expect(byId('editor-saving')).toBeTruthy();
      expect(button('save-version').disabled).toBe(true);
      expect(button('discard-changes').disabled).toBe(true);
      expect(button('change-0').disabled).toBe(true);
      await fixture.componentInstance['save']();
      expect(revise).toHaveBeenCalledTimes(1);
      pending.resolve({ kind: 'ok', plan: NEW_DRAFT });
      await settle(fixture);
      expect(byId('editor-saving')).toBeNull();
    });

    it.each([
      [
        'not_plannable',
        { kind: 'not_plannable' } as RevisePlanResult,
        'cannot be planned any more',
      ],
      [
        'not_revisable',
        { kind: 'not_revisable' } as RevisePlanResult,
        'cannot be changed any more',
      ],
      ['not_found', { kind: 'not_found' } as RevisePlanResult, 'does not exist any more'],
    ])('says when %s, and keeps the changes', async (_name, result, expected) => {
      await setup();
      await click('remove-2');
      revise.mockResolvedValue(result);

      await click('save-version');

      expect(byId('editor-message')?.textContent).toContain(expected);
      expect(titles()).toEqual(['Endurance ride', 'Easy run']);
      expect(saved).not.toHaveBeenCalled();
      expect(button('save-version').disabled).toBe(false);
    });

    it('lists what was wrong with the plan, and keeps the changes', async () => {
      await setup();
      await click('remove-2');
      revise.mockResolvedValue({
        kind: 'invalid',
        problems: [{ path: 'workouts[0].lineage', message: 'A lineage is an id or null.' }],
      });

      await click('save-version');

      expect(byId('editor-problems')?.textContent).toContain('A lineage is an id or null.');
      expect(titles()).toHaveLength(2);
    });

    it('tells the page when the session has ended', async () => {
      await setup();
      await click('remove-2');
      revise.mockResolvedValue({ kind: 'forbidden' });

      await click('save-version');

      expect(signedOut).toHaveBeenCalledTimes(1);
    });

    it('says so when saving fails, and can be tried again', async () => {
      await setup();
      await click('remove-2');
      revise.mockRejectedValueOnce(new Error('down'));

      await click('save-version');

      expect(byId('editor-message')?.textContent).toContain('Something went wrong');
      revise.mockResolvedValue({ kind: 'ok', plan: NEW_DRAFT });
      await click('save-version');
      expect(saved).toHaveBeenCalledTimes(1);
    });
  });

  describe('leaving', () => {
    it('discards the changes without asking anyone anything', async () => {
      await setup();
      await click('remove-0');
      check.mockClear();

      await click('discard-changes');

      expect(cancelled).toHaveBeenCalledTimes(1);
      expect(revise).not.toHaveBeenCalled();
      expect(check).not.toHaveBeenCalled();
    });
  });
});
