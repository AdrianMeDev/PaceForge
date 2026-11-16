import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { GoalsApi } from '../../core/goals/goals-api';
import {
  CreateGoalResult,
  DeleteGoalResult,
  Goal,
  GoalChanges,
  ListGoalsResult,
  UpdateGoalResult,
} from '../../core/goals/goals-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { GoalsPage } from './goals-page';

function goal(changes: Partial<Goal> = {}): Goal {
  return {
    id: 'g1',
    kind: 'race',
    title: 'Berlin Marathon',
    notes: '',
    priority: 'secondary',
    status: 'active',
    target_date: '2027-09-26',
    discipline: 'running',
    distance_m: 42195,
    target_time_seconds: 13500,
    metric: null,
    target_value: null,
    days_to_go: 317,
    assessment: null,
    created_at: '2026-11-13T13:23:19Z',
    updated_at: '2026-11-13T13:23:19Z',
    ...changes,
  };
}

const MAIN = goal({ id: 'main', title: 'Berlin Marathon', priority: 'main' });
const FTP = goal({
  id: 'ftp',
  kind: 'threshold',
  title: 'Raise FTP',
  target_date: '2027-03-01',
  days_to_go: 108,
  assessment: null,
  discipline: null,
  distance_m: null,
  target_time_seconds: null,
  metric: 'ftp',
  target_value: 280,
});
const PACE = goal({
  ...FTP,
  id: 'pace',
  title: 'Faster',
  metric: 'threshold_pace',
  target_value: 300,
});
const GENERAL = goal({
  id: 'general',
  kind: 'general',
  title: 'Build endurance',
  notes: 'Strength as a supplement',
  target_date: null,
  days_to_go: null,
  assessment: null,
  discipline: null,
  distance_m: null,
  target_time_seconds: null,
});
const ACHIEVED = goal({
  id: 'done',
  title: 'First 10k',
  status: 'achieved',
  days_to_go: -30,
  assessment: null,
  target_date: '2026-10-14',
});
const DROPPED = goal({ id: 'dropped', title: 'Ultra', status: 'dropped' });

const ok = (...goals: Goal[]): ListGoalsResult => ({ kind: 'ok', goals });
const updated = (changed: Goal): UpdateGoalResult => ({ kind: 'ok', goal: changed });

function createApiStub() {
  return {
    list: vi.fn<() => Promise<ListGoalsResult>>(),
    create: vi.fn<() => Promise<CreateGoalResult>>(),
    update: vi.fn<(id: string, changes: GoalChanges) => Promise<UpdateGoalResult>>(),
    delete: vi.fn<(id: string) => Promise<DeleteGoalResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('GoalsPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<GoalsPage>;
  let page: HTMLElement;

  async function setup(first: ListGoalsResult = ok(MAIN, FTP, GENERAL)) {
    api = createApiStub();
    api.list.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [GoalsPage],
      providers: [provideRouter([]), { provide: GoalsApi, useValue: api }],
    });
    fixture = TestBed.createComponent(GoalsPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const titles = () =>
    Array.from(page.querySelectorAll('.goal h2')).map((e) => e.textContent?.trim());
  const card = (id: string) => query(page, `[data-testid="goal-${id}"]`);
  const within = (id: string, testId: string) =>
    card(id).querySelector(`[data-testid="${testId}"]`)?.textContent?.replace(/\s+/g, ' ').trim();
  const labelled = (label: string) =>
    page.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);

  function button(label: string): HTMLButtonElement {
    return required(labelled(label), `a button "${label}"`);
  }

  function buttonWithText(label: string): HTMLButtonElement {
    const match = Array.from(page.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(target: HTMLButtonElement): Promise<void> {
    target.click();
    await settle(fixture);
  }

  const buttonsOf = (id: string) =>
    Array.from(card(id).querySelectorAll('button')).map((b) => b.textContent?.trim());

  describe('loading', () => {
    it('shows a loading note until the goals arrive', () => {
      api = createApiStub();
      api.list.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [GoalsPage],
        providers: [provideRouter([]), { provide: GoalsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(GoalsPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('.goal')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the goals cannot be loaded', async () => {
      api = createApiStub();
      api.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(MAIN));
      TestBed.configureTestingModule({
        imports: [GoalsPage],
        providers: [provideRouter([]), { provide: GoalsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(GoalsPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your goals could not be loaded.']);

      await click(buttonWithText('Try again'));

      expect(alerts()).toEqual([]);
      expect(titles()).toEqual(['Berlin Marathon']);
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('.goal')).toBeNull();
    });

    it('shows an empty state', async () => {
      await setup(ok());

      expect(text()).toContain('You have no goals yet.');
      expect(page.querySelector('.goal')).toBeNull();
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup(ok(MAIN, FTP, PACE, GENERAL, ACHIEVED, DROPPED)));

    it('keeps the order the server sent', () => {
      expect(titles()).toEqual([
        'Berlin Marathon',
        'Raise FTP',
        'Faster',
        'Build endurance',
        'First 10k',
        'Ultra',
      ]);
    });

    it('describes the target of each kind', () => {
      expect(within('main', 'target')).toBe('Running · 42.2 km · target 3:45:00');
      expect(within('ftp', 'target')).toBe('FTP 280 W');
      expect(within('pace', 'target')).toBe('Threshold pace 5:00 /km');
      expect(card('general').querySelector('[data-testid="target"]')).toBeNull();
    });

    it('shows the date and how far away it is', () => {
      expect(within('main', 'date')).toBe('Sep 26, 2027 (in 317 days)');
      expect(within('done', 'date')).toBe('Oct 14, 2026 (30 days ago)');
      expect(card('general').querySelector('[data-testid="date"]')).toBeNull();
    });

    it('shows the priority of every goal as A, B or C', async () => {
      TestBed.resetTestingModule();
      await setup(ok(MAIN, FTP, goal({ id: 'tune', title: 'Tune-up', priority: 'preparation' })));

      expect(within('main', 'priority')).toBe('A · Main goal');
      expect(within('ftp', 'priority')).toBe('B · Secondary goal');
      expect(within('tune', 'priority')).toBe('C · Preparation race');
    });

    it('offers to make a preparation race the main goal, and to step down only from A', async () => {
      TestBed.resetTestingModule();
      await setup(ok(MAIN, goal({ id: 'tune', title: 'Tune-up', priority: 'preparation' })));

      expect(buttonsOf('tune')).toContain('Make main goal');
      expect(buttonsOf('tune')).not.toContain('Make secondary');
      expect(buttonsOf('main')).toContain('Make secondary');
    });

    it('names the kind and marks the main goal', () => {
      expect(card('main').textContent).toContain('Race');
      expect(card('main').textContent).toContain('Main goal');
      expect(card('ftp').textContent).toContain('Threshold');
      expect(card('ftp').textContent).not.toContain('Main goal');
      expect(card('general').textContent).toContain('General');
    });

    it('marks finished goals', () => {
      expect(card('done').textContent).toContain('Achieved');
      expect(card('dropped').textContent).toContain('Dropped');
      expect(card('main').textContent).not.toContain('Achieved');
      expect(card('main').textContent).not.toContain('Dropped');
    });

    it('shows the notes', () => {
      expect(within('general', 'notes')).toBe('Strength as a supplement');
      expect(card('main').querySelector('[data-testid="notes"]')).toBeNull();
    });

    it('offers the right buttons for each state', () => {
      expect(buttonsOf('ftp')).toEqual([
        'Mark achieved',
        'Drop',
        'Make main goal',
        'Edit',
        'Delete',
      ]);
      expect(buttonsOf('main')).toEqual([
        'Mark achieved',
        'Drop',
        'Make secondary',
        'Edit',
        'Delete',
      ]);
      expect(buttonsOf('done')).toEqual(['Reactivate', 'Edit', 'Delete']);
      expect(buttonsOf('dropped')).toEqual(['Reactivate', 'Edit', 'Delete']);
    });

    it('names the goal in every button for assistive technology', () => {
      for (const label of [
        'Mark Raise FTP as achieved',
        'Drop Raise FTP',
        'Make Raise FTP the main goal',
        'Make Berlin Marathon a secondary goal',
        'Reactivate First 10k',
        'Delete Ultra',
      ]) {
        expect(labelled(label)).not.toBeNull();
      }
    });
  });

  describe('free text', () => {
    it('shows titles and notes as text and never as markup', async () => {
      await setup(
        ok(
          goal({
            id: 'x',
            title: '<img src=x onerror=alert(1)>',
            notes: '<b>bold</b>\nsecond line',
          }),
        ),
      );

      expect(titles()).toEqual(['<img src=x onerror=alert(1)>']);
      expect(within('x', 'notes')).toContain('<b>bold</b>');
      expect(page.querySelector('img')).toBeNull();
      expect(page.querySelector('.notes b')).toBeNull();
    });
  });

  describe('changing the status', () => {
    it.each([
      ['Mark Raise FTP as achieved', { status: 'achieved' }, 'The goal was marked as achieved.'],
      ['Drop Raise FTP', { status: 'dropped' }, 'The goal was dropped.'],
      ['Make Raise FTP the main goal', { priority: 'main' }, 'The goal is now your main goal.'],
    ])('"%s" sends %j and refreshes the list', async (label, changes, notice) => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue(updated(FTP));
      api.list.mockResolvedValue(ok(MAIN, goal({ ...FTP, status: 'achieved' })));

      await click(button(label));

      expect(api.update).toHaveBeenCalledExactlyOnceWith('ftp', changes);
      expect(api.list).toHaveBeenCalledTimes(2);
      expect(text()).toContain(notice);
    });

    it('shows the new state from the refreshed list', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue(updated(FTP));
      api.list.mockResolvedValue(ok(MAIN, goal({ ...FTP, status: 'achieved' })));

      await click(button('Mark Raise FTP as achieved'));

      expect(card('ftp').textContent).toContain('Achieved');
      expect(buttonsOf('ftp')).toEqual(['Reactivate', 'Edit', 'Delete']);
    });

    it('lets a main goal step down', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue(updated(MAIN));
      api.list.mockResolvedValue(ok(goal({ ...MAIN, priority: 'secondary' }), FTP));

      await click(button('Make Berlin Marathon a secondary goal'));

      expect(api.update).toHaveBeenCalledExactlyOnceWith('main', { priority: 'secondary' });
      expect(card('main').textContent).not.toContain('Main goal');
      expect(text()).toContain('The goal is now a secondary goal.');
    });

    it('brings a finished goal back', async () => {
      await setup(ok(ACHIEVED));
      api.update.mockResolvedValue(updated(ACHIEVED));
      api.list.mockResolvedValue(ok(goal({ ...ACHIEVED, status: 'active' })));

      await click(button('Reactivate First 10k'));

      expect(api.update).toHaveBeenCalledExactlyOnceWith('done', { status: 'active' });
      expect(text()).toContain('The goal is active again.');
    });

    it('shows the message of the server when there already is a main goal', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue({
        kind: 'invalid',
        errors: ['You already have a main goal. Change it first.'],
        fields: { priority: ['You already have a main goal. Change it first.'] },
      });

      await click(button('Make Raise FTP the main goal'));

      expect(alerts()).toEqual(['You already have a main goal. Change it first.']);
      expect(api.list).toHaveBeenCalledTimes(1);
      expect(card('ftp').textContent).not.toContain('Main goal');
    });

    it('shows the message of the server when a past race cannot be reactivated', async () => {
      await setup(ok(ACHIEVED));
      api.update.mockResolvedValue({
        kind: 'invalid',
        errors: ['An active race cannot lie in the past.'],
        fields: {},
      });

      await click(button('Reactivate First 10k'));

      expect(alerts()).toEqual(['An active race cannot lie in the past.']);
    });

    it('clears an earlier message with the next action', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValueOnce({ kind: 'invalid', errors: ['No.'], fields: {} });
      api.update.mockResolvedValueOnce(updated(FTP));
      await click(button('Make Raise FTP the main goal'));

      await click(button('Drop Raise FTP'));

      expect(alerts()).toEqual([]);
    });

    it('says when the goal is gone and refreshes the list', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok(MAIN));

      await click(button('Drop Raise FTP'));

      expect(alerts()).toEqual(['That goal does not exist any more.']);
      expect(titles()).toEqual(['Berlin Marathon']);
    });

    it('shows the sign-in note when the session ended', async () => {
      await setup(ok(MAIN));
      api.update.mockResolvedValue({ kind: 'forbidden' });

      await click(button('Drop Berlin Marathon'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when the change does not work and keeps the list', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockRejectedValue(new Error('offline'));

      await click(button('Drop Raise FTP'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(titles()).toEqual(['Berlin Marathon', 'Raise FTP']);
    });

    it('keeps the old list and says so when the refresh fails', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue(updated(FTP));
      api.list.mockRejectedValue(new Error('offline'));

      await click(button('Drop Raise FTP'));

      expect(alerts()).toEqual(['The list could not be refreshed. Please try again.']);
      expect(titles()).toEqual(['Berlin Marathon', 'Raise FTP']);
      expect(text()).toContain('The goal was dropped.');
    });

    it('shows the sign-in note when the refresh finds the session gone', async () => {
      await setup(ok(MAIN, FTP));
      api.update.mockResolvedValue(updated(FTP));
      api.list.mockResolvedValue({ kind: 'forbidden' });

      await click(button('Drop Raise FTP'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('sends only once when a button is clicked twice in a row', async () => {
      await setup(ok(MAIN, FTP));
      const pending = deferred<UpdateGoalResult>();
      api.update.mockReturnValue(pending.promise);

      const target = button('Drop Raise FTP');
      target.click();
      target.click();
      pending.resolve(updated(FTP));
      await settle(fixture);

      expect(api.update).toHaveBeenCalledTimes(1);
    });

    it('disables every button while one action runs', async () => {
      await setup(ok(MAIN, FTP));
      const pending = deferred<UpdateGoalResult>();
      api.update.mockReturnValue(pending.promise);

      button('Drop Raise FTP').click();
      fixture.detectChanges();

      expect(Array.from(page.querySelectorAll('button')).every((b) => b.disabled)).toBe(true);
      pending.resolve(updated(FTP));
      await settle(fixture);
      expect(Array.from(page.querySelectorAll('button')).some((b) => b.disabled)).toBe(false);
    });
  });

  describe('adding and editing', () => {
    const SAVED_GOAL = goal({ id: 'new', title: 'New goal' });
    const formTitle = () => page.querySelector<HTMLInputElement>('#goal-title');

    async function fillAndSave(title: string): Promise<void> {
      typeInto(page, '#goal-title', title);
      typeInto(page, '#goal-date', '2027-09-26');
      const discipline = query<HTMLSelectElement>(page, '#goal-discipline');
      discipline.value = 'running';
      discipline.dispatchEvent(new Event('change'));
      await settle(fixture);
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await settle(fixture);
    }

    beforeEach(() => setup(ok(MAIN, FTP)));

    it('offers to add a goal and opens an empty form', async () => {
      expect(formTitle()).toBeNull();

      await click(buttonWithText('Add goal'));

      expect(formTitle()?.value).toBe('');
      expect(query(page, 'h2:not(.goal h2)').textContent).toBe('Add goal');
      expect(page.querySelector('.panel button')).not.toBeNull();
    });

    it('hides the add button while the form is open', async () => {
      await click(buttonWithText('Add goal'));

      expect(
        Array.from(page.querySelectorAll('button')).filter(
          (b) => b.textContent?.trim() === 'Add goal',
        ),
      ).toHaveLength(1);
      expect(page.querySelector('p > button.primary')).toBeNull();
    });

    it('closes the form again with Cancel and sends nothing', async () => {
      await click(buttonWithText('Add goal'));

      await click(buttonWithText('Cancel'));

      expect(formTitle()).toBeNull();
      expect(api.create).not.toHaveBeenCalled();
      expect(buttonWithText('Add goal')).toBeTruthy();
    });

    it('saves a new goal, closes the form, says so and fetches the list again', async () => {
      api.create.mockResolvedValue({ kind: 'ok', goal: SAVED_GOAL });
      api.list.mockResolvedValue(ok(MAIN, FTP, SAVED_GOAL));
      await click(buttonWithText('Add goal'));

      await fillAndSave('New goal');

      expect(api.create).toHaveBeenCalledTimes(1);
      expect(formTitle()).toBeNull();
      expect(text()).toContain('The goal was saved.');
      expect(api.list).toHaveBeenCalledTimes(2);
      expect(titles()).toEqual(['Berlin Marathon', 'Raise FTP', 'New goal']);
    });

    it('keeps the form and its entries when the server refuses', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['An active race cannot lie in the past.'],
        fields: { target_date: ['An active race cannot lie in the past.'] },
      });
      await click(buttonWithText('Add goal'));

      await fillAndSave('New goal');

      expect(formTitle()?.value).toBe('New goal');
      expect(alerts()).toEqual(['An active race cannot lie in the past.']);
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('opens the goal in the form with its data', async () => {
      await click(button('Edit Raise FTP'));

      expect(query(page, 'h2:not(.goal h2)').textContent).toBe('Edit goal');
      expect(formTitle()?.value).toBe('Raise FTP');
    });

    it('sends the changes to that goal', async () => {
      api.update.mockResolvedValue(updated(FTP));
      await click(button('Edit Raise FTP'));
      typeInto(page, '#goal-title', 'Raise FTP to 290');
      typeInto(page, '#goal-value', '290');
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await settle(fixture);

      expect(api.update).toHaveBeenCalledTimes(1);
      expect(api.update.mock.calls[0][0]).toBe('ftp');
      expect(api.update.mock.calls[0][1]).toMatchObject({
        title: 'Raise FTP to 290',
        target_value: 290,
      });
      expect(formTitle()).toBeNull();
      expect(text()).toContain('The goal was saved.');
    });

    it('shows the form of the goal that was chosen last', async () => {
      await click(button('Edit Raise FTP'));
      await click(button('Edit Berlin Marathon'));

      expect(page.querySelectorAll('form')).toHaveLength(1);
      expect(formTitle()?.value).toBe('Berlin Marathon');
    });

    it('changes from editing to adding with an empty form', async () => {
      await click(button('Edit Raise FTP'));
      await click(buttonWithText('Cancel'));
      await click(buttonWithText('Add goal'));

      expect(formTitle()?.value).toBe('');
    });

    it('clears an earlier message when the form opens', async () => {
      api.update.mockResolvedValue({ kind: 'invalid', errors: ['No.'], fields: {} });
      await click(button('Drop Raise FTP'));
      expect(alerts()).toEqual(['No.']);

      await click(buttonWithText('Add goal'));

      expect(alerts()).toEqual([]);
    });

    it('closes an open delete question when the form for a new goal opens', async () => {
      await click(button('Delete Raise FTP'));
      expect(text()).toContain('Delete this goal?');

      await click(buttonWithText('Add goal'));

      expect(text()).not.toContain('Delete this goal?');
    });

    it('clears an earlier message when a goal is opened for editing', async () => {
      api.update.mockResolvedValue({ kind: 'invalid', errors: ['No.'], fields: {} });
      await click(button('Drop Raise FTP'));
      expect(alerts()).toEqual(['No.']);

      await click(button('Edit Berlin Marathon'));

      expect(alerts()).toEqual([]);
    });

    it('closes an open delete question when the form opens', async () => {
      await click(button('Delete Raise FTP'));
      expect(text()).toContain('Delete this goal?');

      await click(button('Edit Berlin Marathon'));

      expect(text()).not.toContain('Delete this goal?');
    });

    it('says when the goal being edited is gone, closes the form and refreshes', async () => {
      api.update.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok(MAIN));
      await click(button('Edit Raise FTP'));
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await settle(fixture);

      expect(formTitle()).toBeNull();
      expect(alerts()).toEqual(['That goal does not exist any more.']);
      expect(titles()).toEqual(['Berlin Marathon']);
    });

    it('shows the sign-in note when the session ended while saving', async () => {
      api.update.mockResolvedValue({ kind: 'forbidden' });
      await click(button('Edit Raise FTP'));
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(formTitle()).toBeNull();
    });

    it('offers no "Add goal" on an empty list without it', async () => {
      TestBed.resetTestingModule();
      await setup(ok());

      expect(text()).toContain('You have no goals yet.');
      expect(buttonWithText('Add goal')).toBeTruthy();
    });
  });

  describe('deleting', () => {
    beforeEach(() => setup(ok(MAIN, FTP)));

    it('asks first and deletes nothing until confirmed', async () => {
      await click(button('Delete Raise FTP'));

      expect(text()).toContain('Delete this goal?');
      expect(api.delete).not.toHaveBeenCalled();
    });

    it('does nothing when cancelled', async () => {
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Cancel'));

      expect(api.delete).not.toHaveBeenCalled();
      expect(text()).not.toContain('Delete this goal?');
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('clears an earlier message when it asks', async () => {
      api.update.mockResolvedValue({ kind: 'invalid', errors: ['No.'], fields: {} });
      await click(button('Drop Raise FTP'));
      expect(alerts()).toEqual(['No.']);

      await click(button('Delete Raise FTP'));

      expect(alerts()).toEqual([]);
    });

    it('asks about one goal at a time', async () => {
      await click(button('Delete Raise FTP'));
      await click(button('Delete Berlin Marathon'));

      expect(page.querySelectorAll('.confirm')).toHaveLength(1);
      expect(query(page, '.confirm').getAttribute('aria-label')).toBe('Delete Berlin Marathon');
    });

    it('deletes the confirmed goal and refreshes the list', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok(MAIN));
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Yes, delete'));

      expect(api.delete).toHaveBeenCalledExactlyOnceWith('ftp');
      expect(titles()).toEqual(['Berlin Marathon']);
      expect(text()).toContain('The goal was deleted.');
    });

    it('treats a goal that is already gone as deleted', async () => {
      api.delete.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok(MAIN));
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Yes, delete'));

      expect(text()).toContain('That goal does not exist any more.');
      expect(titles()).toEqual(['Berlin Marathon']);
    });

    it('shows the empty state after the last goal is deleted', async () => {
      api.delete.mockResolvedValue({ kind: 'deleted' });
      api.list.mockResolvedValue(ok());
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Yes, delete'));

      expect(text()).toContain('You have no goals yet.');
    });

    it('shows the sign-in note when the session ended', async () => {
      api.delete.mockResolvedValue({ kind: 'forbidden' });
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Yes, delete'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when deleting does not work and keeps the goal', async () => {
      api.delete.mockRejectedValue(new Error('offline'));
      await click(button('Delete Raise FTP'));

      await click(buttonWithText('Yes, delete'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(titles()).toEqual(['Berlin Marathon', 'Raise FTP']);
    });

    it('deletes only once when confirmed twice in a row', async () => {
      const pending = deferred<DeleteGoalResult>();
      api.delete.mockReturnValue(pending.promise);
      await click(button('Delete Raise FTP'));

      const confirm = buttonWithText('Yes, delete');
      confirm.click();
      confirm.click();
      pending.resolve({ kind: 'deleted' });
      await settle(fixture);

      expect(api.delete).toHaveBeenCalledTimes(1);
    });
  });
});
