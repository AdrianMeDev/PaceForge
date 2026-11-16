import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EditedWorkout } from '../../core/planning/planning-models';
import { query } from '../../testing/dom';
import { WorkoutForm } from './workout-form';

const WEEK = '2026-11-16';

const RIDE: EditedWorkout = {
  lineage: '01a1d73d-aaaa-7000-8000-000000000001',
  day: '2026-11-16',
  sport: 'cycling',
  title: 'Endurance ride',
  goal: 'endurance',
  duration_minutes: 90,
  zone_system: 'power',
  zone: 2,
  notes: 'Keep it easy',
  slot: 'morning',
  stretching_minutes: 10,
  exercises: [],
  segments: [],
};

const INTERVALS: EditedWorkout = {
  lineage: '01a1d73d-aaaa-7000-8000-000000000002',
  day: '2026-11-18',
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
  segments: [
    { kind: 'warmup', seconds: 900, repeat: 1, zone_system: 'pace', zone: 2 },
    { kind: 'work', seconds: 600, repeat: 3, zone_system: 'pace', zone: 4 },
  ],
};

const LIFTING: EditedWorkout = {
  lineage: '01a1d73d-aaaa-7000-8000-000000000003',
  day: '2026-11-17',
  sport: 'strength',
  title: 'Strength',
  goal: 'strength',
  duration_minutes: 45,
  zone_system: null,
  zone: null,
  notes: '',
  slot: null,
  stretching_minutes: 0,
  segments: [],
  exercises: [
    {
      name: 'Goblet squat',
      region: 'legs',
      equipment: 'dumbbells',
      sets: 3,
      reps: 10,
      seconds: null,
      rpe: 7,
      rest_seconds: 90,
    },
    {
      name: 'Plank',
      region: 'core',
      equipment: 'bodyweight',
      sets: 3,
      reps: null,
      seconds: 45,
      rpe: null,
      rest_seconds: null,
    },
  ],
};

describe('WorkoutForm', () => {
  let fixture: ComponentFixture<WorkoutForm>;
  let page: HTMLElement;
  const saved = vi.fn<(workout: EditedWorkout) => void>();
  const cancelled = vi.fn();

  function setup(workout: EditedWorkout | null = null, day: string | null = null) {
    saved.mockClear();
    cancelled.mockClear();
    TestBed.configureTestingModule({ imports: [WorkoutForm] });
    fixture = TestBed.createComponent(WorkoutForm);
    fixture.componentRef.setInput('week', WEEK);
    fixture.componentRef.setInput('workout', workout);
    fixture.componentRef.setInput('day', day);
    fixture.componentInstance.saved.subscribe(saved);
    fixture.componentInstance.cancelled.subscribe(cancelled);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  const select = (id: string) => query<HTMLSelectElement>(page, `#${id}`);
  const input = (id: string) => query<HTMLInputElement>(page, `#${id}`);
  const area = (id: string) => query<HTMLTextAreaElement>(page, `#${id}`);
  const error = (name: string) =>
    page.querySelector(`[data-testid="error-${name}"]`)?.textContent?.trim();
  const options = (id: string) => Array.from(select(id).options).map((o) => o.value);

  function choose(id: string, value: string) {
    const element = select(id);
    element.value = value;
    element.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function type(id: string, value: string) {
    const element = query<HTMLInputElement | HTMLTextAreaElement>(page, `#${id}`);
    element.value = value;
    element.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function submit() {
    query<HTMLButtonElement>(page, '[data-testid="workout-save"]').click();
    fixture.detectChanges();
  }

  function lastSaved(): EditedWorkout {
    expect(saved).toHaveBeenCalled();
    return saved.mock.calls[saved.mock.calls.length - 1][0];
  }

  describe('a new workout', () => {
    it('starts as an easy hour of running on the first day of the week', () => {
      setup();

      expect(page.querySelector('h3')?.textContent).toBe('Add a workout');
      expect(select('workout-day').value).toBe('2026-11-16');
      expect(select('workout-sport').value).toBe('running');
      expect(select('workout-goal').value).toBe('endurance');
      expect(select('workout-slot').value).toBe('');
      expect(input('workout-title').value).toBe('');
      expect(input('workout-duration').value).toBe('60');
      expect(input('workout-stretching').value).toBe('');
      expect(query(page, '[data-testid="workout-save"]').textContent?.trim()).toBe('Add workout');
    });

    it('starts on the day it is given', () => {
      setup(null, '2026-11-19');

      expect(select('workout-day').value).toBe('2026-11-19');
    });

    it('offers the seven days of the week', () => {
      setup();

      expect(options('workout-day')).toEqual([
        '2026-11-16',
        '2026-11-17',
        '2026-11-18',
        '2026-11-19',
        '2026-11-20',
        '2026-11-21',
        '2026-11-22',
      ]);
    });

    it('is saved without a lineage, as a new workout', () => {
      setup();
      type('workout-title', '  Evening jog  ');
      choose('workout-slot', 'evening');
      choose('workout-day', '2026-11-20');

      submit();

      expect(lastSaved()).toEqual({
        lineage: null,
        day: '2026-11-20',
        sport: 'running',
        title: 'Evening jog',
        goal: 'endurance',
        duration_minutes: 60,
        zone_system: null,
        zone: null,
        notes: '',
        slot: 'evening',
        stretching_minutes: 0,
        exercises: [],
        segments: [],
      });
    });

    it('needs a title', () => {
      setup();

      submit();

      expect(error('title')).toBe('Enter a title.');
      expect(saved).not.toHaveBeenCalled();
    });
  });

  describe('a workout that is changed', () => {
    it('shows what the workout is', () => {
      setup(RIDE);

      expect(page.querySelector('h3')?.textContent).toBe('Change this workout');
      expect(select('workout-day').value).toBe('2026-11-16');
      expect(select('workout-slot').value).toBe('morning');
      expect(select('workout-sport').value).toBe('cycling');
      expect(select('workout-goal').value).toBe('endurance');
      expect(input('workout-title').value).toBe('Endurance ride');
      expect(input('workout-duration').value).toBe('90');
      expect(select('workout-zone-system').value).toBe('power');
      expect(select('workout-zone').value).toBe('2');
      expect(input('workout-stretching').value).toBe('10');
      expect(area('workout-notes').value).toBe('Keep it easy');
      expect(query(page, '[data-testid="workout-save"]').textContent?.trim()).toBe('Save workout');
    });

    it('is saved as it was when nothing is changed, with its lineage', () => {
      setup(RIDE);

      submit();

      expect(lastSaved()).toEqual(RIDE);
    });

    it('is moved by changing its day and its time of day', () => {
      setup(RIDE);

      choose('workout-day', '2026-11-20');
      choose('workout-slot', 'evening');
      submit();

      expect(lastSaved()).toEqual({ ...RIDE, day: '2026-11-20', slot: 'evening' });
    });

    it('can lose its time of day', () => {
      setup(RIDE);

      choose('workout-slot', '');
      submit();

      expect(lastSaved().slot).toBeNull();
    });

    it('can be changed in every other field', () => {
      setup(RIDE);

      type('workout-title', 'Hill repeats');
      choose('workout-goal', 'vo2max');
      type('workout-duration', '1:15');
      type('workout-stretching', '15');
      type('workout-notes', '  Short and sharp  ');
      choose('workout-zone', '5');
      submit();

      expect(lastSaved()).toEqual({
        ...RIDE,
        title: 'Hill repeats',
        goal: 'vo2max',
        duration_minutes: 75,
        stretching_minutes: 15,
        exercises: [],
        notes: 'Short and sharp',
        zone: 5,
      });
    });

    it('starts again from the new workout when it is given another one', () => {
      setup(RIDE);
      type('workout-title', 'Typed');

      fixture.componentRef.setInput('workout', INTERVALS);
      fixture.detectChanges();

      expect(input('workout-title').value).toBe('Intervals');
      expect(select('workout-day').value).toBe('2026-11-18');
    });
  });

  describe('the target', () => {
    it('offers the zone systems of the sport', () => {
      setup(RIDE);
      expect(options('workout-zone-system')).toEqual(['', 'power', 'heart_rate']);

      choose('workout-sport', 'running');

      expect(options('workout-zone-system')).toEqual(['', 'pace', 'heart_rate']);
    });

    it('offers no target for swimming and strength', () => {
      setup(RIDE);

      choose('workout-sport', 'swimming');

      expect(page.querySelector('#workout-zone-system')).toBeNull();
      expect(page.querySelector('#workout-zone')).toBeNull();
    });

    it('drops a target that does not fit the new sport', () => {
      setup(RIDE);

      choose('workout-sport', 'running');
      submit();

      expect(lastSaved()).toMatchObject({ sport: 'running', zone_system: null, zone: null });
    });

    it('keeps a target that fits the new sport but asks for the zone again', () => {
      setup(RIDE);
      choose('workout-zone-system', 'heart_rate');

      choose('workout-sport', 'running');
      submit();

      expect(select('workout-zone-system').value).toBe('heart_rate');
      expect(error('zone')).toBe('Choose a zone.');
    });

    it('offers as many zones as the system has', () => {
      setup(RIDE);
      expect(options('workout-zone')).toEqual(['', '1', '2', '3', '4', '5', '6', '7']);

      choose('workout-zone-system', 'heart_rate');

      expect(options('workout-zone')).toEqual(['', '1', '2', '3', '4', '5']);
    });

    it('needs a zone once a system is chosen', () => {
      setup(null);
      type('workout-title', 'Ride');
      choose('workout-sport', 'cycling');
      choose('workout-zone-system', 'power');

      submit();

      expect(error('zone')).toBe('Choose a zone.');
      expect(saved).not.toHaveBeenCalled();
    });

    it('is saved as a system with a zone', () => {
      setup(null);
      type('workout-title', 'Ride');
      choose('workout-sport', 'cycling');
      choose('workout-zone-system', 'power');
      choose('workout-zone', '3');

      submit();

      expect(lastSaved()).toMatchObject({ sport: 'cycling', zone_system: 'power', zone: 3 });
    });

    it('can be taken away', () => {
      setup(RIDE);

      choose('workout-zone-system', '');
      submit();

      expect(lastSaved()).toMatchObject({ zone_system: null, zone: null });
      expect(page.querySelector('#workout-zone')).toBeNull();
    });
  });

  describe('what is refused', () => {
    it.each([
      ['', 'Enter the duration as minutes (90) or hours and minutes (1:30).'],
      ['abc', 'Enter the duration as minutes (90) or hours and minutes (1:30).'],
      ['0', 'Use a duration from 1 minute to 24 hours.'],
      ['1441', 'Use a duration from 1 minute to 24 hours.'],
    ])('a duration of %j', (text, message) => {
      setup(RIDE);

      type('workout-duration', text);
      submit();

      expect(error('duration')).toBe(message);
      expect(saved).not.toHaveBeenCalled();
    });

    it('stretching of more than an hour', () => {
      setup(RIDE);

      type('workout-stretching', '61');
      submit();

      expect(error('stretching')).toBe('Enter whole minutes from 0 to 60.');
    });

    it('a title of more than 100 characters, or with a control character in it', () => {
      setup(RIDE);

      type('workout-title', 't'.repeat(101));
      submit();
      expect(error('title')).toBe('Use at most 100 characters.');

      // A text field cannot hold a line break, but it can hold other control characters.
      type('workout-title', 'bell' + String.fromCharCode(7));
      submit();
      expect(error('title')).toBe('A title is one line of plain text.');
      expect(saved).not.toHaveBeenCalled();
    });

    it('notes of more than 500 characters', () => {
      setup(RIDE);

      type('workout-notes', 'n'.repeat(501));
      submit();

      expect(error('notes')).toBe('Use at most 500 characters.');
    });

    it('takes a title and notes of exactly the limit', () => {
      setup(RIDE);

      type('workout-title', 't'.repeat(100));
      type('workout-notes', 'n'.repeat(500));
      submit();

      expect(lastSaved().title).toHaveLength(100);
      expect(lastSaved().notes).toHaveLength(500);
    });

    it('reports every problem at once, and keeps what was typed', () => {
      setup(RIDE);
      type('workout-title', '   ');
      type('workout-duration', '0');
      type('workout-stretching', 'x');
      type('workout-notes', 'n'.repeat(501));

      submit();

      expect(error('title')).toBe('Enter a title.');
      expect(error('duration')).toBeTruthy();
      expect(error('stretching')).toBeTruthy();
      expect(error('notes')).toBeTruthy();
      expect(input('workout-duration').value).toBe('0');
      expect(input('workout-stretching').value).toBe('x');
      expect(area('workout-notes').value).toHaveLength(501);
      expect(saved).not.toHaveBeenCalled();
    });

    it('drops the messages of an earlier try when it is saved', () => {
      setup(RIDE);
      type('workout-title', '');
      submit();
      expect(error('title')).toBeTruthy();

      type('workout-title', 'Fixed');
      submit();

      expect(error('title')).toBeUndefined();
      expect(lastSaved().title).toBe('Fixed');
    });
  });

  describe('an interval structure', () => {
    it('is kept as it is, and the duration follows it', () => {
      setup(INTERVALS);

      expect(input('workout-duration').readOnly).toBe(true);
      expect(input('workout-duration').value).toBe('1 h 10 min');
      expect(query(page, '[data-testid="structure-hint"]').textContent).toContain('kept as it is');

      choose('workout-day', '2026-11-19');
      submit();

      expect(lastSaved()).toEqual({ ...INTERVALS, day: '2026-11-19' });
    });

    it('can be removed, and then the duration is the one in the field', () => {
      setup(INTERVALS);

      const box = input('workout-drop-structure');
      box.checked = true;
      box.dispatchEvent(new Event('change'));
      fixture.detectChanges();
      expect(input('workout-duration').readOnly).toBe(false);
      expect(input('workout-duration').value).toBe('70');
      expect(query(page, '[data-testid="structure-hint"]').textContent).toContain('is removed');

      type('workout-duration', '45');
      submit();

      expect(lastSaved()).toEqual({ ...INTERVALS, duration_minutes: 45, segments: [] });
    });

    it('is not offered for a workout without one', () => {
      setup(RIDE);

      expect(page.querySelector('#workout-drop-structure')).toBeNull();
      expect(input('workout-duration').readOnly).toBe(false);
    });

    it('is not touched by the duration field while it is kept', () => {
      setup(INTERVALS);

      submit();

      expect(lastSaved().duration_minutes).toBe(70);
      expect(error('duration')).toBeUndefined();
    });

    it('is kept again for the next workout', () => {
      setup(INTERVALS);
      const box = input('workout-drop-structure');
      box.checked = true;
      box.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      fixture.componentRef.setInput('workout', { ...INTERVALS, lineage: RIDE.lineage });
      fixture.detectChanges();

      expect(input('workout-drop-structure').checked).toBe(false);
      expect(input('workout-duration').readOnly).toBe(true);
    });
  });

  describe('leaving', () => {
    it('is cancelled without saving anything', () => {
      setup(RIDE);
      type('workout-title', 'Changed');

      query<HTMLButtonElement>(page, '[data-testid="workout-cancel"]').click();

      expect(cancelled).toHaveBeenCalledTimes(1);
      expect(saved).not.toHaveBeenCalled();
    });

    it('does not submit the page when Enter is pressed in a field', () => {
      setup(RIDE);
      const form = query<HTMLFormElement>(page, 'form');
      const event = new Event('submit', { cancelable: true });

      form.dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
      expect(saved).toHaveBeenCalledTimes(1);
    });
  });

  describe('the exercises of a strength workout', () => {
    it('stay when the workout is changed', () => {
      setup(LIFTING);
      type('workout-duration', '50');

      submit();

      expect(lastSaved().exercises).toEqual(LIFTING.exercises);
      expect(lastSaved().duration_minutes).toBe(50);
    });

    it('go when the sport is no longer strength', () => {
      setup(LIFTING);
      choose('workout-sport', 'running');

      submit();

      expect(lastSaved()).toMatchObject({ sport: 'running', exercises: [] });
    });

    it('are none for a workout that never had any', () => {
      setup(RIDE);

      submit();

      expect(lastSaved().exercises).toEqual([]);
    });

    const hint = () => page.querySelector('[data-testid="exercises-hint"]')?.textContent;

    it('are announced in the form with their number', () => {
      setup(LIFTING);

      expect(hint()?.replace(/\s+/g, ' ').trim()).toBe(
        'This workout has 2 exercises; they are kept as they are.',
      );
    });

    it('say so in the singular for one', () => {
      setup({ ...LIFTING, exercises: [LIFTING.exercises[0]] });

      expect(hint()?.replace(/\s+/g, ' ').trim()).toBe(
        'This workout has 1 exercise; they are kept as they are.',
      );
    });

    it('are announced as removed when the sport is changed away from strength', () => {
      setup(LIFTING);
      choose('workout-sport', 'cycling');

      expect(hint()?.trim()).toBe(
        'The exercises are removed when you save, because the sport is not strength any more.',
      );
    });

    it('are announced as kept again when the sport is changed back', () => {
      setup(LIFTING);
      choose('workout-sport', 'cycling');
      choose('workout-sport', 'strength');

      expect(hint()).toContain('kept as they are');
      submit();
      expect(lastSaved().exercises).toEqual(LIFTING.exercises);
    });

    it('say nothing for a workout without any', () => {
      setup(RIDE);

      expect(hint()).toBeUndefined();
    });

    it('are not added to a workout that becomes strength', () => {
      setup(RIDE);
      choose('workout-sport', 'strength');

      submit();

      expect(lastSaved()).toMatchObject({ sport: 'strength', exercises: [] });
    });
  });
});
