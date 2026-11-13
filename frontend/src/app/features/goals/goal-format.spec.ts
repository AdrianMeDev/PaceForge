import { Goal } from '../../core/goals/goals-models';
import { daysToGoText, describeTarget, formatGoalDistance } from './goal-format';

const goal = (changes: Partial<Goal>): Goal => ({
  id: 'g1',
  kind: 'general',
  title: 'x',
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
  created_at: '2026-11-13T00:00:00Z',
  updated_at: '2026-11-13T00:00:00Z',
  ...changes,
});

describe('formatGoalDistance', () => {
  it.each([
    [42195, '42.2 km'],
    [21097.5, '21.1 km'],
    [5000, '5 km'],
    [10000, '10 km'],
    [226000, '226 km'],
    [1000, '1 km'],
    [999.4, '999 m'],
    [800, '800 m'],
    [1_000_000, '1000 km'],
  ])('shows %f metres as %s', (meters, text) => {
    expect(formatGoalDistance(meters)).toBe(text);
  });
});

describe('daysToGoText', () => {
  it.each([
    [0, 'today'],
    [1, 'tomorrow'],
    [-1, 'yesterday'],
    [2, 'in 2 days'],
    [12, 'in 12 days'],
    [317, 'in 317 days'],
    [-2, '2 days ago'],
    [-30, '30 days ago'],
  ])('says %i days as "%s"', (days, text) => {
    expect(daysToGoText(days)).toBe(text);
  });

  it('says nothing for a goal without a date', () => {
    expect(daysToGoText(null)).toBe('');
  });
});

describe('describeTarget', () => {
  it('describes a race with everything it has', () => {
    expect(
      describeTarget(
        goal({
          kind: 'race',
          discipline: 'running',
          distance_m: 42195,
          target_time_seconds: 13500,
        }),
      ),
    ).toBe('Running · 42.2 km · target 3:45:00');
  });

  it.each([
    [{ discipline: 'cycling', distance_m: null, target_time_seconds: null }, 'Cycling'],
    [{ discipline: 'running', distance_m: 10000, target_time_seconds: null }, 'Running · 10 km'],
    [
      { discipline: 'triathlon', distance_m: null, target_time_seconds: 40000 },
      'Triathlon · target 11:06:40',
    ],
    [
      { discipline: 'swimming', distance_m: 800, target_time_seconds: 1500 },
      'Swimming · 800 m · target 25:00',
    ],
  ] as const)('leaves out what a race does not have (%j)', (fields, text) => {
    expect(describeTarget(goal({ kind: 'race', ...fields }))).toBe(text);
  });

  it.each([
    [{ metric: 'ftp', target_value: 280 }, 'FTP 280 W'],
    [{ metric: 'threshold_pace', target_value: 300 }, 'Threshold pace 5:00 /km'],
  ] as const)('describes a threshold goal (%j)', (fields, text) => {
    expect(describeTarget(goal({ kind: 'threshold', ...fields }))).toBe(text);
  });

  it('goes by the kind, whatever else the goal carries', () => {
    const odd = { metric: 'ftp', target_value: 280, discipline: 'running' } as const;

    expect(describeTarget(goal({ kind: 'race', ...odd }))).toBe('Running');
    expect(describeTarget(goal({ kind: 'general', ...odd }))).toBe('');
    expect(describeTarget(goal({ kind: 'threshold', ...odd, distance_m: 5000 }))).toBe('FTP 280 W');
  });

  it('has nothing to say for a general goal, whatever its notes', () => {
    expect(describeTarget(goal({ kind: 'general', notes: 'Build endurance' }))).toBe('');
  });

  it('has nothing to say for a threshold goal that lacks its target', () => {
    expect(describeTarget(goal({ kind: 'threshold', metric: 'ftp', target_value: null }))).toBe('');
  });
});
