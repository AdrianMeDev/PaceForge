import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Workout } from '../../core/planning/planning-models';
import { query } from '../../testing/dom';
import { PlanDay, PlanDayView } from './plan-day';

function workout(changes: Partial<Workout>): Workout {
  return {
    lineage: '01a1d73d-aaaa-7000-8000-000000000001',
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

describe('PlanDayView', () => {
  let fixture: ComponentFixture<PlanDayView>;

  function show(day: PlanDay): HTMLElement {
    fixture = TestBed.createComponent(PlanDayView);
    fixture.componentRef.setInput('day', day);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  it('shows the day and a workout with its title, sport, slot and duration', () => {
    const page = show({
      date: '2026-11-16',
      label: 'Monday, Nov 16',
      workouts: [{ number: 1, workout: workout({}) }],
    });

    expect(query(page, 'h3').textContent?.trim()).toBe('Monday, Nov 16');
    expect(query(page, '.workout h4').textContent).toBe('Endurance ride');
    expect(query(page, '[data-testid=slot]').textContent).toBe('Morning');
    expect(query(page, '[data-testid=meta]').textContent).toContain('1 h');
    expect(query(page, '[data-testid=workout-1]')).toBeTruthy();
  });

  it('marks each workout with the icon of its sport', () => {
    const page = show({
      date: '2026-11-16',
      label: 'Monday, Nov 16',
      workouts: [
        { number: 1, workout: workout({ sport: 'running' }) },
        { number: 2, workout: workout({ sport: 'swimming' }) },
      ],
    });

    const icons = Array.from(page.querySelectorAll('app-icon')).map((icon) =>
      icon.getAttribute('aria-label'),
    );
    expect(icons).toEqual(['Running', 'Swimming']);
  });

  it('colours the state of a send', () => {
    const page = show({
      date: '2026-11-16',
      label: 'Monday, Nov 16',
      workouts: [
        {
          number: 1,
          workout: workout({
            export: { status: 'failed', error_code: 'rejected', pushed_at: null },
          }),
        },
      ],
    });

    expect(query(page, '[data-testid=export]').className).toContain('text-danger');
  });

  it('lists the exercises of a strength workout and its stretching', () => {
    const page = show({
      date: '2026-11-17',
      label: 'Tuesday, Nov 17',
      workouts: [
        {
          number: 2,
          workout: workout({
            sport: 'strength',
            title: 'Legs',
            stretching_minutes: 10,
            exercises: [
              {
                name: 'Squat',
                region: 'legs',
                equipment: 'gym',
                sets: 3,
                reps: 8,
                seconds: null,
                rpe: null,
                rest_seconds: null,
              },
            ],
          }),
        },
      ],
    });

    expect(page.querySelectorAll('.exercises li')).toHaveLength(1);
    expect(query(page, '.exercise-name').textContent).toBe('Squat');
    expect(query(page, '[data-testid=stretching]')).toBeTruthy();
  });

  it('shows only the heading for a day without workouts', () => {
    const page = show({ date: '2026-11-18', label: 'Wednesday, Nov 18', workouts: [] });

    expect(query(page, 'h3').textContent?.trim()).toBe('Wednesday, Nov 18');
    expect(page.querySelectorAll('.workout')).toHaveLength(0);
  });
});
