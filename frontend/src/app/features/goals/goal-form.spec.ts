import { ComponentFixture, TestBed } from '@angular/core/testing';
import { GoalsApi } from '../../core/goals/goals-api';
import {
  CreateGoalResult,
  Goal,
  GoalChanges,
  GoalInput,
  UpdateGoalResult,
} from '../../core/goals/goals-models';
import { query, settle, typeInto } from '../../testing/dom';
import { GoalForm } from './goal-form';

const SAVED: Goal = {
  id: 'new',
  kind: 'general',
  title: 'Saved',
  notes: '',
  priority: 'secondary',
  status: 'active',
  target_date: null,
  discipline: null,
  distance_m: null,
  target_time_seconds: null,
  metric: null,
  target_value: null,
  days_to_go: null,
  created_at: '2026-11-13T13:23:19Z',
  updated_at: '2026-11-13T13:23:19Z',
};

const RACE: Goal = {
  ...SAVED,
  id: 'race',
  kind: 'race',
  title: 'Berlin Marathon',
  notes: 'A-race',
  priority: 'main',
  target_date: '2027-09-26',
  discipline: 'running',
  distance_m: 42195,
  target_time_seconds: 13500,
  days_to_go: 317,
};

const THRESHOLD: Goal = {
  ...SAVED,
  id: 'ftp',
  kind: 'threshold',
  title: 'Raise FTP',
  metric: 'threshold_pace',
  target_value: 285,
};

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('GoalForm', () => {
  let api: {
    create: ReturnType<typeof vi.fn<(input: GoalInput) => Promise<CreateGoalResult>>>;
    update: ReturnType<
      typeof vi.fn<(id: string, changes: GoalChanges) => Promise<UpdateGoalResult>>
    >;
  };
  let fixture: ComponentFixture<GoalForm>;
  let form: HTMLElement;
  let saved: Goal[];
  let events: string[];

  async function setup(goal: Goal | null = null) {
    api = { create: vi.fn(), update: vi.fn() };
    api.create.mockResolvedValue({ kind: 'ok', goal: SAVED });
    api.update.mockResolvedValue({ kind: 'ok', goal: SAVED });
    TestBed.configureTestingModule({
      imports: [GoalForm],
      providers: [{ provide: GoalsApi, useValue: api }],
    });
    fixture = TestBed.createComponent(GoalForm);
    fixture.componentRef.setInput('goal', goal);
    saved = [];
    events = [];
    fixture.componentInstance.saved.subscribe((g) => saved.push(g));
    fixture.componentInstance.cancelled.subscribe(() => events.push('cancelled'));
    fixture.componentInstance.signedOut.subscribe(() => events.push('signedOut'));
    fixture.componentInstance.gone.subscribe(() => events.push('gone'));
    form = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  async function choose(selector: string, value: string): Promise<void> {
    const select = query<HTMLSelectElement>(form, selector);
    select.value = value;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function type(selector: string, value: string): Promise<void> {
    typeInto(form, selector, value);
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(form.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const has = (selector: string) => form.querySelector(selector) !== null;
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(form, selector).value;

  async function fillRace(): Promise<void> {
    await type('#goal-title', '  Berlin Marathon ');
    await choose('#goal-discipline', 'running');
    await type('#goal-date', '2027-09-26');
  }

  describe('adding', () => {
    beforeEach(() => setup());

    it('is headed "Add goal", offers the kinds and starts with a race', () => {
      expect(query(form, 'h2').textContent).toBe('Add goal');
      expect(
        Array.from(form.querySelectorAll('#goal-kind option')).map((o) => o.textContent?.trim()),
      ).toEqual(['Race', 'Threshold', 'General']);
      expect(value('#goal-kind')).toBe('race');
      expect(has('#goal-discipline')).toBe(true);
    });

    it('puts the cursor in the title', async () => {
      TestBed.resetTestingModule();
      await setup();
      document.body.appendChild(form);
      try {
        fixture.destroy();
        fixture = TestBed.createComponent(GoalForm);
        document.body.appendChild(fixture.nativeElement);
        fixture.detectChanges();
        await settle(fixture);

        expect(document.activeElement?.id).toBe('goal-title');
      } finally {
        document.body.replaceChildren();
      }
    });

    it('sends a race with its distance and time', async () => {
      await fillRace();
      await choose('#goal-distance', '42195');
      await type('#goal-time', '3:45:00');

      await submit();

      expect(api.create).toHaveBeenCalledExactlyOnceWith({
        kind: 'race',
        title: 'Berlin Marathon',
        notes: '',
        priority: 'secondary',
        target_date: '2027-09-26',
        discipline: 'running',
        distance_m: 42195,
        target_time_seconds: 13500,
      });
      expect(saved).toEqual([SAVED]);
    });

    it('sends a race without distance and time as nulls', async () => {
      await fillRace();

      await submit();

      expect(api.create).toHaveBeenCalledExactlyOnceWith({
        kind: 'race',
        title: 'Berlin Marathon',
        notes: '',
        priority: 'secondary',
        target_date: '2027-09-26',
        discipline: 'running',
        distance_m: null,
        target_time_seconds: null,
      });
    });

    it('takes any other distance in kilometres', async () => {
      await fillRace();
      expect(has('#goal-distance-km')).toBe(false);

      await choose('#goal-distance', 'other');
      await type('#goal-distance-km', '15,5');
      await submit();

      expect(api.create.mock.calls[0][0].distance_m).toBe(15500);
    });

    it('says when the other distance is not usable', async () => {
      await fillRace();
      await choose('#goal-distance', 'other');
      await type('#goal-distance-km', 'far');

      await submit();

      expect(alerts()).toEqual(['Enter a number, for example 21.1.']);
      expect(query(form, '#goal-distance-km').getAttribute('aria-invalid')).toBe('true');
      expect(api.create).not.toHaveBeenCalled();
    });

    it('offers the distances of the chosen discipline only', async () => {
      const options = () =>
        Array.from(form.querySelectorAll('#goal-distance option')).map((o) =>
          o.textContent?.trim(),
        );
      expect(options()).toEqual(['No distance', 'Other distance']);

      await choose('#goal-discipline', 'running');
      expect(options()).toEqual([
        'No distance',
        '5 km',
        '10 km',
        'Half marathon',
        'Marathon',
        'Other distance',
      ]);

      await choose('#goal-discipline', 'triathlon');
      expect(options()).toContain('Ironman (226 km)');
      expect(options()).not.toContain('Marathon');

      await choose('#goal-discipline', 'cycling');
      expect(options()).toEqual(['No distance', 'Other distance']);
    });

    it('drops a distance that the new discipline does not offer, but keeps "other"', async () => {
      await choose('#goal-discipline', 'running');
      await choose('#goal-distance', '42195');
      await choose('#goal-discipline', 'cycling');
      expect(value('#goal-distance')).toBe('');

      await choose('#goal-distance', 'other');
      await type('#goal-distance-km', '100');
      await choose('#goal-discipline', 'running');
      expect(value('#goal-distance')).toBe('other');
      expect(value('#goal-distance-km')).toBe('100');
    });

    it('starts the other distance empty each time it is chosen', async () => {
      await choose('#goal-discipline', 'running');
      await choose('#goal-distance', 'other');
      await type('#goal-distance-km', '15');
      await choose('#goal-distance', '5000');
      await choose('#goal-distance', 'other');

      expect(value('#goal-distance-km')).toBe('');
    });

    it('keeps a distance the new discipline offers as well', async () => {
      await choose('#goal-discipline', 'running');
      await choose('#goal-distance', '5000');
      await choose('#goal-discipline', 'running');

      expect(value('#goal-distance')).toBe('5000');
    });

    it('asks for what a race needs and names the field', async () => {
      await submit();

      expect(alerts()).toEqual([
        'Enter a title.',
        'Choose a discipline.',
        'Enter the date of the race.',
      ]);
      expect(query(form, '#goal-title').getAttribute('aria-invalid')).toBe('true');
      expect(query(form, '#goal-title').getAttribute('aria-describedby')).toBe('goal-title-error');
      expect(api.create).not.toHaveBeenCalled();
    });

    it('treats a title of spaces as empty', async () => {
      await type('#goal-title', '    ');
      await submit();

      expect(alerts()[0]).toBe('Enter a title.');
    });

    it('refuses a title of more than 100 characters but takes exactly 100', async () => {
      await fillRace();
      await type('#goal-title', 'x'.repeat(101));
      await submit();
      expect(alerts()).toEqual(['Use at most 100 characters.']);

      await type('#goal-title', 'x'.repeat(100));
      await submit();
      expect(api.create).toHaveBeenCalledTimes(1);
    });

    it('refuses notes of more than 1000 characters but takes exactly 1000', async () => {
      await fillRace();
      await type('#goal-notes', 'n'.repeat(1001));
      await submit();
      expect(alerts()).toEqual(['Use at most 1000 characters.']);

      await type('#goal-notes', 'n'.repeat(1000));
      await submit();
      expect(api.create).toHaveBeenCalledTimes(1);
    });

    it('refuses a target time that is not a time', async () => {
      await fillRace();
      await type('#goal-time', 'soon');

      await submit();

      expect(alerts()).toEqual([
        'Enter the time as hours, minutes and seconds, for example 3:45:00.',
      ]);
      expect(api.create).not.toHaveBeenCalled();
    });

    it('sends the priority and the notes', async () => {
      await fillRace();
      await choose('#goal-priority', 'main');
      await type('#goal-notes', 'A-race');

      await submit();

      expect(api.create.mock.calls[0][0]).toMatchObject({ priority: 'main', notes: 'A-race' });
    });

    it('sends a threshold goal for the FTP', async () => {
      await choose('#goal-kind', 'threshold');
      expect(has('#goal-discipline')).toBe(false);
      await type('#goal-title', 'Raise FTP');
      await type('#goal-value', '280');

      await submit();

      expect(api.create).toHaveBeenCalledExactlyOnceWith({
        kind: 'threshold',
        title: 'Raise FTP',
        notes: '',
        priority: 'secondary',
        target_date: null,
        metric: 'ftp',
        target_value: 280,
      });
    });

    it('sends a threshold goal for the pace in seconds per kilometre', async () => {
      await choose('#goal-kind', 'threshold');
      await choose('#goal-metric', 'threshold_pace');
      await type('#goal-title', 'Faster');
      await type('#goal-value', '4:45');
      await type('#goal-date', '2027-03-01');

      await submit();

      expect(api.create.mock.calls[0][0]).toMatchObject({
        metric: 'threshold_pace',
        target_value: 285,
        target_date: '2027-03-01',
      });
    });

    it('explains the value for each metric', async () => {
      await choose('#goal-kind', 'threshold');
      expect(query(form, '#goal-value-hint').textContent).toContain('Watts');

      await choose('#goal-metric', 'threshold_pace');
      expect(query(form, '#goal-value-hint').textContent).toContain('per kilometre');
    });

    it('refuses a target value that is not plausible', async () => {
      await choose('#goal-kind', 'threshold');
      await type('#goal-title', 'Raise FTP');
      await type('#goal-value', '5');

      await submit();

      expect(alerts()).toHaveLength(1);
      expect(query(form, '#goal-value').getAttribute('aria-invalid')).toBe('true');
      expect(api.create).not.toHaveBeenCalled();
    });

    it('asks for the value of a threshold goal', async () => {
      await choose('#goal-kind', 'threshold');
      await type('#goal-title', 'Raise FTP');

      await submit();

      expect(alerts()).toEqual(['Enter a value.']);
    });

    it('sends a general goal with the title alone', async () => {
      await choose('#goal-kind', 'general');
      expect(has('#goal-discipline')).toBe(false);
      expect(has('#goal-value')).toBe(false);
      await type('#goal-title', 'Build endurance');

      await submit();

      expect(api.create).toHaveBeenCalledExactlyOnceWith({
        kind: 'general',
        title: 'Build endurance',
        notes: '',
        priority: 'secondary',
        target_date: null,
      });
    });

    it('does not carry race fields over into another kind', async () => {
      await fillRace();
      await choose('#goal-kind', 'general');

      await submit();

      expect(Object.keys(api.create.mock.calls[0][0]).sort()).toEqual(
        ['kind', 'notes', 'priority', 'target_date', 'title'].sort(),
      );
    });

    it('keeps the date entered when the kind changes', async () => {
      await type('#goal-date', '2027-09-26');
      await choose('#goal-kind', 'general');

      expect(value('#goal-date')).toBe('2027-09-26');
    });

    it('asks nothing of a general goal but a title', async () => {
      await choose('#goal-kind', 'general');

      await submit();

      expect(alerts()).toEqual(['Enter a title.']);
    });

    it('cancels', async () => {
      query<HTMLButtonElement>(form, 'button.link').click();

      expect(events).toEqual(['cancelled']);
      expect(api.create).not.toHaveBeenCalled();
    });
  });

  describe('what the server says', () => {
    beforeEach(async () => {
      await setup();
      await fillRace();
    });

    it('shows a message next to its field', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['An active race cannot lie in the past.'],
        fields: { target_date: ['An active race cannot lie in the past.'] },
      });

      await submit();

      expect(alerts()).toEqual(['An active race cannot lie in the past.']);
      expect(query(form, '#goal-date-error').textContent).toContain('past');
      expect(saved).toEqual([]);
    });

    it.each([
      ['title', '#goal-title-error'],
      ['discipline', '#goal-discipline-error'],
      ['distance_m', '#goal-distance-error'],
    ])('places a message for "%s"', async (field, errorId) => {
      await choose('#goal-distance', 'other');
      await type('#goal-distance-km', '10');
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['Nope.'],
        fields: { [field]: ['Nope.'] },
      });

      await submit();

      expect(query(form, errorId).textContent).toBe('Nope.');
    });

    it('shows a message for the main goal next to the priority', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['You already have a main goal. Change it first.'],
        fields: { priority: ['You already have a main goal. Change it first.'] },
      });

      await submit();

      expect(alerts()).toEqual(['You already have a main goal. Change it first.']);
    });

    it('shows a problem of the whole goal at the top of the form', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['You can have at most 30 goals.'],
        fields: { non_field_errors: ['You can have at most 30 goals.'] },
      });

      await submit();

      expect(alerts()).toEqual(['You can have at most 30 goals.']);
      expect(query(form, 'form > .alert').textContent).toContain('30 goals');
    });

    it('shows the list of messages when there are no fields', async () => {
      api.create.mockResolvedValue({ kind: 'invalid', errors: ['One.', 'Two.'], fields: {} });

      await submit();

      expect(alerts()).toEqual(['One. Two.']);
    });

    it('joins several messages for one field', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['A.', 'B.'],
        fields: { title: ['A.', 'B.'] },
      });

      await submit();

      expect(query(form, '#goal-title-error').textContent).toBe('A. B.');
    });

    it('collects the messages of fields the form does not know in one place', async () => {
      api.create.mockResolvedValue({
        kind: 'invalid',
        errors: ['A.', 'B.'],
        fields: { non_field_errors: ['A.'], something_else: ['B.'] },
      });

      await submit();

      expect(alerts()).toEqual(['A. B.']);
    });

    it('clears the messages with the next try', async () => {
      api.create.mockResolvedValueOnce({ kind: 'invalid', errors: ['No.'], fields: {} });
      await submit();
      expect(alerts()).toEqual(['No.']);

      await submit();

      expect(alerts()).toEqual([]);
      expect(saved).toEqual([SAVED]);
    });

    it('says so when saving does not work', async () => {
      api.create.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(saved).toEqual([]);
    });

    it('reports a gone session', async () => {
      api.create.mockResolvedValue({ kind: 'forbidden' });

      await submit();

      expect(events).toEqual(['signedOut']);
    });

    it('sends only once when submitted twice in a row, and shows that it is saving', async () => {
      const pending = deferred<CreateGoalResult>();
      api.create.mockReturnValue(pending.promise);

      query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      query<HTMLFormElement>(form, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await fixture.whenStable();
      fixture.detectChanges();
      const button = query<HTMLButtonElement>(form, 'button[type="submit"]');
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Saving');
      pending.resolve({ kind: 'ok', goal: SAVED });
      await settle(fixture);

      expect(api.create).toHaveBeenCalledTimes(1);
      expect(button.disabled).toBe(false);
    });

    it('does not let the browser submit the page', async () => {
      const event = new Event('submit', { cancelable: true });
      query<HTMLFormElement>(form, 'form').dispatchEvent(event);
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
    });
  });

  describe('changing a race', () => {
    beforeEach(() => setup(RACE));

    it('is headed "Edit goal" and shows the kind without a choice', () => {
      expect(query(form, 'h2').textContent).toBe('Edit goal');
      expect(has('#goal-kind')).toBe(false);
      expect(query(form, '.fixed').textContent).toContain('Race');
      expect(query<HTMLButtonElement>(form, 'button[type="submit"]').textContent).toContain(
        'Save changes',
      );
    });

    it('starts with what the goal has', () => {
      expect(value('#goal-title')).toBe('Berlin Marathon');
      expect(value('#goal-notes')).toBe('A-race');
      expect(value('#goal-priority')).toBe('main');
      expect(value('#goal-date')).toBe('2027-09-26');
      expect(value('#goal-discipline')).toBe('running');
      expect(value('#goal-distance')).toBe('42195');
      expect(value('#goal-time')).toBe('3:45:00');
    });

    it('sends the changes without the kind, to the goal', async () => {
      await type('#goal-title', 'Berlin 2027');

      await submit();

      expect(api.update).toHaveBeenCalledExactlyOnceWith('race', {
        title: 'Berlin 2027',
        notes: 'A-race',
        priority: 'main',
        target_date: '2027-09-26',
        discipline: 'running',
        distance_m: 42195,
        target_time_seconds: 13500,
      });
      expect(api.create).not.toHaveBeenCalled();
      expect(saved).toEqual([SAVED]);
    });

    it('can remove the target time', async () => {
      await type('#goal-time', '');

      await submit();

      expect(api.update.mock.calls[0][1].target_time_seconds).toBeNull();
    });

    it('reports a goal that is gone', async () => {
      api.update.mockResolvedValue({ kind: 'not_found' });

      await submit();

      expect(events).toEqual(['gone']);
    });

    it('reports a gone session', async () => {
      api.update.mockResolvedValue({ kind: 'forbidden' });

      await submit();

      expect(events).toEqual(['signedOut']);
    });

    it('shows what the server refuses', async () => {
      api.update.mockResolvedValue({
        kind: 'invalid',
        errors: ['You already have a main goal. Change it first.'],
        fields: { priority: ['You already have a main goal. Change it first.'] },
      });

      await submit();

      expect(alerts()).toEqual(['You already have a main goal. Change it first.']);
      expect(saved).toEqual([]);
    });
  });

  describe('changing other goals', () => {
    it('shows a distance that is not a preset in kilometres, under "other"', async () => {
      await setup({ ...RACE, distance_m: 15500 });

      expect(value('#goal-distance')).toBe('other');
      expect(value('#goal-distance-km')).toBe('15.5');
    });

    it('shows a race without a distance or a time', async () => {
      await setup({ ...RACE, distance_m: null, target_time_seconds: null });

      expect(value('#goal-distance')).toBe('');
      expect(value('#goal-time')).toBe('');
      expect(has('#goal-distance-km')).toBe(false);
    });

    it('shows a threshold goal with its pace as minutes and seconds', async () => {
      await setup(THRESHOLD);

      expect(value('#goal-metric')).toBe('threshold_pace');
      expect(value('#goal-value')).toBe('4:45');
      expect(value('#goal-date')).toBe('');
    });

    it('sends a threshold change with the metric and the value', async () => {
      await setup(THRESHOLD);
      await type('#goal-value', '4:30');

      await submit();

      expect(api.update).toHaveBeenCalledExactlyOnceWith('ftp', {
        title: 'Raise FTP',
        notes: '',
        priority: 'secondary',
        target_date: null,
        metric: 'threshold_pace',
        target_value: 270,
      });
    });

    it('shows a general goal with the title and the notes only', async () => {
      await setup({ ...SAVED, id: 'g', title: 'Build', notes: 'Strength' });

      expect(value('#goal-title')).toBe('Build');
      expect(value('#goal-notes')).toBe('Strength');
      expect(has('#goal-discipline')).toBe(false);
      expect(has('#goal-metric')).toBe(false);
    });
  });
});
