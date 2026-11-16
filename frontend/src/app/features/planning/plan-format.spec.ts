import { Exercise, Segment } from '../../core/planning/planning-models';
import {
  EQUIPMENT_LABELS,
  GOAL_LABELS,
  REGION_LABELS,
  SLOT_LABELS,
  SPORT_LABELS,
  STATUS_LABELS,
  dayLabel,
  exerciseDetail,
  findingPlace,
  minutesText,
  exportSummaryText,
  exportText,
  pushText,
  rangeText,
  segmentText,
  stretchingText,
  targetText,
  weekRange,
} from './plan-format';

function segment(changes: Partial<Segment> = {}): Segment {
  return {
    kind: 'work',
    seconds: 600,
    repeat: 1,
    zone_system: null,
    zone: null,
    target: null,
    ...changes,
  };
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

  it('adds the numbers of the zone when it has them', () => {
    expect(targetText('power', 2, { low: 138, high: 188, unit: 'W' })).toBe(
      'Power zone 2 · 138–188 W',
    );
  });

  it('stays as it is if the zone has no numbers', () => {
    expect(targetText('power', 2, null)).toBe('Power zone 2');
  });

  it('says nothing about numbers without a zone', () => {
    expect(targetText(null, null, { low: 138, high: 188, unit: 'W' })).toBe('');
  });
});

describe('rangeText', () => {
  it.each([
    [{ low: 138, high: 188, unit: 'W' }, '138–188 W'],
    [{ low: 145, high: 152, unit: 'bpm' }, '145–152 bpm'],
    [{ low: 312, high: 341, unit: 's/km' }, '5:12–5:41 /km'],
    [{ low: 245, high: 305, unit: 's/km' }, '4:05–5:05 /km'],
  ] as const)('writes %j as "%s"', (range, expected) => {
    expect(rangeText(range)).toBe(expected);
  });

  it('is empty without a range', () => {
    expect(rangeText(null)).toBe('');
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

function exercise(changes: Partial<Exercise> = {}): Exercise {
  return {
    name: 'Goblet squat',
    region: 'legs',
    equipment: 'dumbbells',
    sets: 3,
    reps: 10,
    seconds: null,
    rpe: null,
    rest_seconds: null,
    ...changes,
  };
}

describe('exerciseDetail', () => {
  it('writes the sets and the repetitions', () => {
    expect(exerciseDetail(exercise())).toBe('3 × 10');
  });

  it('writes a hold in seconds', () => {
    expect(exerciseDetail(exercise({ reps: null, seconds: 45 }))).toBe('3 × 45 s');
  });

  it('adds the RPE and the rest if they are given', () => {
    expect(exerciseDetail(exercise({ rpe: 7, rest_seconds: 90 }))).toBe(
      '3 × 10 · RPE 7 · rest 1:30',
    );
    expect(exerciseDetail(exercise({ rest_seconds: 60 }))).toBe('3 × 10 · rest 1:00');
    expect(exerciseDetail(exercise({ rpe: 8 }))).toBe('3 × 10 · RPE 8');
  });

  it('writes a rest below ten seconds with two digits and no rest as nothing', () => {
    expect(exerciseDetail(exercise({ rest_seconds: 5 }))).toBe('3 × 10 · rest 0:05');
    expect(exerciseDetail(exercise({ rest_seconds: 0 }))).toBe('3 × 10 · rest 0:00');
  });
});

describe('the labels of exercises', () => {
  it('name every region and every kind of equipment', () => {
    expect(REGION_LABELS).toEqual({
      legs: 'Legs',
      core: 'Core',
      upper_body: 'Upper body',
      full_body: 'Full body',
    });
    expect(EQUIPMENT_LABELS).toEqual({
      gym: 'Gym',
      dumbbells: 'Dumbbells',
      bodyweight: 'Body weight',
    });
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

  it('shows the numbers of the zone', () => {
    expect(
      segmentText(
        segment({
          repeat: 4,
          zone_system: 'power',
          zone: 4,
          target: { low: 248, high: 300, unit: 'W' },
        }),
      ),
    ).toBe('4 × 10 min work, power zone 4 · 248–300 W');
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

describe('exportText', () => {
  it.each([
    [{ status: 'synced', error_code: '', pushed_at: 't' }, 'In Intervals.icu'],
    [{ status: 'not_sent', error_code: '', pushed_at: null }, 'Not sent to Intervals.icu yet'],
    [
      { status: 'failed', error_code: 'rejected', pushed_at: 't' },
      'Not sent: Intervals.icu did not accept this workout.',
    ],
    [
      { status: 'failed', error_code: 'unavailable', pushed_at: 't' },
      'Not sent: Intervals.icu could not be reached.',
    ],
    [
      { status: 'failed', error_code: 'unexpected', pushed_at: 't' },
      'Not sent: Intervals.icu answered in an unexpected way.',
    ],
  ] as const)('writes %j as "%s"', (state, expected) => {
    expect(exportText(state)).toBe(expected);
  });
});

describe('exportSummaryText', () => {
  it.each([
    [{ synced: 0, failed: 0, not_sent: 3, older: 0 }, 'Not sent to Intervals.icu yet.'],
    [{ synced: 3, failed: 0, not_sent: 0, older: 0 }, '3 of 3 workouts in Intervals.icu.'],
    [{ synced: 1, failed: 0, not_sent: 0, older: 0 }, '1 of 1 workout in Intervals.icu.'],
    [
      { synced: 1, failed: 1, not_sent: 1, older: 0 },
      '1 of 3 workouts in Intervals.icu. 1 could not be sent. 1 not sent yet.',
    ],
    [
      { synced: 0, failed: 2, not_sent: 0, older: 0 },
      '0 of 2 workouts in Intervals.icu. 2 could not be sent.',
    ],
    [
      { synced: 0, failed: 0, not_sent: 2, older: 4 },
      'Not sent to Intervals.icu yet. Events of an older version are still in Intervals.icu; sending replaces them.',
    ],
    [{ synced: 0, failed: 0, not_sent: 0, older: 0 }, ''],
  ])('writes %j as "%s"', (summary, expected) => {
    expect(exportSummaryText(summary)).toBe(expected);
  });
});

describe('pushText', () => {
  it.each([
    [
      { synced: 4, failed: 0, removed: 0, left_behind: 0 },
      '4 workouts were sent to Intervals.icu.',
    ],
    [{ synced: 1, failed: 0, removed: 0, left_behind: 0 }, '1 workout was sent to Intervals.icu.'],
    [
      { synced: 2, failed: 1, removed: 3, left_behind: 1 },
      '2 workouts were sent to Intervals.icu. 1 workout could not be sent. ' +
        '3 events of an older version removed. 1 event could not be removed yet.',
    ],
    [{ synced: 0, failed: 0, removed: 0, left_behind: 0 }, 'There was nothing to send.'],
  ])('writes %j as "%s"', (outcome, expected) => {
    expect(pushText({ ok: true, ...outcome })).toBe(expected);
  });

  it('gives the text of the server for a problem', () => {
    expect(pushText({ ok: false, problem: 'not_connected', message: 'Not connected.' })).toBe(
      'Not connected.',
    );
  });
});
