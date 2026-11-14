import { Segment } from '../../core/planning/planning-models';
import {
  GOAL_LABELS,
  SLOT_LABELS,
  SPORT_LABELS,
  STATUS_LABELS,
  dayLabel,
  findingPlace,
  minutesText,
  segmentText,
  stretchingText,
  targetText,
  weekRange,
} from './plan-format';

function segment(changes: Partial<Segment> = {}): Segment {
  return { kind: 'work', seconds: 600, repeat: 1, zone_system: null, zone: null, ...changes };
}

describe('labels', () => {
  it('name every sport, goal and status in words', () => {
    expect(SPORT_LABELS).toEqual({
      running: 'Running',
      cycling: 'Cycling',
      swimming: 'Swimming',
      strength: 'Strength',
    });
    expect(GOAL_LABELS).toEqual({
      recovery: 'Recovery',
      endurance: 'Endurance',
      tempo: 'Tempo',
      threshold: 'Threshold',
      vo2max: 'VO2max',
      strength: 'Strength',
      other: 'Other',
    });
    expect(STATUS_LABELS).toEqual({
      draft: 'Draft',
      confirmed: 'Confirmed',
      superseded: 'Replaced',
      discarded: 'Discarded',
    });
  });
});

describe('dayLabel', () => {
  it.each([
    ['2026-11-16', 'Mon 16 Nov'],
    ['2026-11-22', 'Sun 22 Nov'],
    ['2027-01-01', 'Fri 1 Jan'],
    ['2028-02-29', 'Tue 29 Feb'],
    ['2026-12-31', 'Thu 31 Dec'],
  ])('writes %s as %s', (date, expected) => {
    expect(dayLabel(date)).toBe(expected);
  });
});

describe('weekRange', () => {
  it.each([
    ['2026-11-16', '16 Nov – 22 Nov'],
    ['2026-11-30', '30 Nov – 6 Dec'],
    ['2026-10-26', '26 Oct – 1 Nov'],
    ['2026-12-28', '28 Dec – 3 Jan'],
    ['2028-02-28', '28 Feb – 5 Mar'],
    ['2026-11-23', '23 Nov – 29 Nov'],
  ])('writes the week of %s as %s', (monday, expected) => {
    expect(weekRange(monday)).toBe(expected);
  });
});

describe('minutesText', () => {
  it.each([
    [1, '1 min'],
    [45, '45 min'],
    [59, '59 min'],
    [60, '1 h'],
    [90, '1 h 30 min'],
    [125, '2 h 5 min'],
    [120, '2 h'],
    [1440, '24 h'],
  ])('writes %i minutes as %s', (minutes, expected) => {
    expect(minutesText(minutes)).toBe(expected);
  });
});

describe('targetText', () => {
  it.each([
    ['power', 2, 'Power zone 2'],
    ['heart_rate', 3, 'Heart rate zone 3'],
    ['pace', 5, 'Pace zone 5'],
  ] as const)('writes %s zone %i as "%s"', (system, zone, expected) => {
    expect(targetText(system, zone)).toBe(expected);
  });

  it('is empty without a target', () => {
    expect(targetText(null, null)).toBe('');
  });
});

describe('SLOT_LABELS', () => {
  it('names the three times of day in words', () => {
    expect(SLOT_LABELS).toEqual({ morning: 'Morning', afternoon: 'Afternoon', evening: 'Evening' });
  });
});

describe('stretchingText', () => {
  it.each([
    [1, '+ 1 min stretching'],
    [10, '+ 10 min stretching'],
    [60, '+ 60 min stretching'],
  ])('writes %i minutes as "%s"', (minutes, expected) => {
    expect(stretchingText(minutes)).toBe(expected);
  });

  it('says nothing for no stretching', () => {
    expect(stretchingText(0)).toBe('');
  });
});

describe('segmentText', () => {
  it('writes the length, the kind and the target', () => {
    expect(segmentText(segment({ zone_system: 'power', zone: 4 }))).toBe(
      '10 min work, power zone 4',
    );
  });

  it('writes a repeat before the length', () => {
    expect(segmentText(segment({ repeat: 3, zone_system: 'pace', zone: 4 }))).toBe(
      '3 × 10 min work, pace zone 4',
    );
  });

  it('leaves out the target if there is none', () => {
    expect(segmentText(segment({ kind: 'steady', seconds: 1800 }))).toBe('30 min steady');
  });

  it.each([
    [30, '30 s'],
    [90, '1 min 30 s'],
    [900, '15 min'],
    [3600, '60 min'],
  ])('writes %i seconds as %s', (seconds, length) => {
    expect(segmentText(segment({ seconds }))).toBe(`${length} work`);
  });

  it.each([
    ['warmup', 'warm-up'],
    ['steady', 'steady'],
    ['work', 'work'],
    ['recovery', 'recovery'],
    ['cooldown', 'cool-down'],
  ] as const)('writes the kind %s as %s', (kind, word) => {
    expect(segmentText(segment({ kind }))).toBe(`10 min ${word}`);
  });

  it('writes a repeat of 2', () => {
    expect(segmentText(segment({ repeat: 2 }))).toBe('2 × 10 min work');
  });

  it('does not count a repeat of 1', () => {
    expect(segmentText(segment({ repeat: 1 }))).toBe('10 min work');
  });
});

describe('findingPlace', () => {
  it.each([
    ['workouts[0]', 'Workout 1'],
    ['workouts[2].segments', 'Workout 3'],
    ['workouts[11].day', 'Workout 12'],
    ['', 'Week'],
    ['rationale', 'Week'],
    ['week_start', 'Week'],
    ['xworkouts[1]', 'Week'],
  ])('puts "%s" at %s', (path, expected) => {
    expect(findingPlace(path)).toBe(expected);
  });
});
