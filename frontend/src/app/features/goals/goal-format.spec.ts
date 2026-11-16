import { Assessment, Goal } from '../../core/goals/goals-models';
import {
  DISTANCE_PRESETS,
  daysToGoText,
  describeTarget,
  figuresText,
  formatGoalDistance,
  judgementText,
  kilometresText,
  parseDistanceKm,
  parseTargetTime,
  preparationText,
  PRIORITY_LABELS,
  RATING_LABELS,
  REASON_TEXTS,
  suggestedTarget,
  suggestionText,
} from './goal-format';
import { formatDuration } from '../activities/activity-format';

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
  assessment: null,
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

describe('parseTargetTime', () => {
  it.each([
    ['3:45:00', 13500],
    ['3:45:01', 13501],
    ['0:30:00', 1800],
    ['45:30', 2730],
    ['1:05', 65],
    ['01:00', 60],
    ['200:00', 12000],
    [' 3:45:00 ', 13500],
    ['100:00:00', 360000],
    ['1:59:59', 7199],
  ])('reads "%s" as %i seconds', (text, seconds) => {
    expect(parseTargetTime(text)).toEqual({ ok: true, value: seconds });
  });

  it.each(['', '   '])('treats an empty field ("%s") as no target', (text) => {
    expect(parseTargetTime(text)).toEqual({ ok: true, value: null });
  });

  it.each([
    'abc',
    '3:75:00',
    '3:45:60',
    '45:60',
    '3:5:00',
    '3:45:0',
    '3',
    '3:',
    ':45',
    '3,45',
    '3.45.00',
    '1:2:3:4',
    '-3:45:00',
    '3:45:00x',
    '1234:00',
  ])('does not read "%s" as a time', (text) => {
    expect(parseTargetTime(text)).toEqual({
      ok: false,
      error: 'Enter the time as hours, minutes and seconds, for example 3:45:00.',
    });
  });

  it.each(['0:59', '0:00', '0:00:30', '100:00:01', '999:00:00'])(
    'refuses "%s" as out of range',
    (text) => {
      expect(parseTargetTime(text)).toEqual({
        ok: false,
        error: 'Enter a time between 1 minute and 100 hours.',
      });
    },
  );

  it('gives back what the page shows', () => {
    for (const seconds of [60, 1800, 2730, 3600, 13500, 40000, 360000]) {
      expect(parseTargetTime(formatDuration(seconds))).toEqual({ ok: true, value: seconds });
    }
  });
});

describe('parseDistanceKm', () => {
  it.each([
    ['42.195', 42195],
    ['42,195', 42195],
    ['21.0975', 21097.5],
    ['5', 5000],
    [' 10 ', 10000],
    ['0.8', 800],
    ['1000', 1_000_000],
  ])('reads "%s" km as %f metres', (text, meters) => {
    expect(parseDistanceKm(text)).toEqual({ ok: true, value: meters });
  });

  it.each(['', '   '])('asks for a distance when the field is empty ("%s")', (text) => {
    expect(parseDistanceKm(text)).toEqual({ ok: false, error: 'Enter the distance in km.' });
  });

  it.each(['far', '5km', '-5', '1e3', '.5', '5.', '1 000'])('does not read "%s"', (text) => {
    expect(parseDistanceKm(text)).toEqual({
      ok: false,
      error: 'Enter a number, for example 21.1.',
    });
  });

  it.each(['0', '0.0', '1000.1', '5000'])('refuses "%s" as out of range', (text) => {
    expect(parseDistanceKm(text)).toEqual({
      ok: false,
      error: 'Enter a distance between 0 and 1000 km.',
    });
  });

  it('gives back what a field shows', () => {
    for (const meters of [800, 5000, 21097.5, 42195, 226000, 1_000_000]) {
      expect(parseDistanceKm(kilometresText(meters))).toEqual({ ok: true, value: meters });
    }
  });
});

describe('kilometresText', () => {
  it.each([
    [42195, '42.195'],
    [5000, '5'],
    [800, '0.8'],
    [21097.5, '21.0975'],
  ])('shows %f metres as "%s"', (meters, text) => {
    expect(kilometresText(meters)).toBe(text);
  });
});

describe('the distance presets', () => {
  it('are written out on purpose', () => {
    expect(DISTANCE_PRESETS.running.map((p) => [p.label, p.meters])).toEqual([
      ['5 km', 5000],
      ['10 km', 10000],
      ['Half marathon', 21097.5],
      ['Marathon', 42195],
    ]);
    expect(DISTANCE_PRESETS.triathlon.map((p) => p.meters)).toEqual([25750, 51500, 113000, 226000]);
    expect(DISTANCE_PRESETS.cycling).toEqual([]);
    expect(DISTANCE_PRESETS.swimming).toEqual([]);
  });
});

describe('the priority labels', () => {
  it('name A, B and C', () => {
    expect(PRIORITY_LABELS).toEqual({
      main: 'A · Main goal',
      secondary: 'B · Secondary goal',
      preparation: 'C · Preparation race',
    });
  });
});

const assessment = (changes: Partial<Assessment> = {}): Assessment => ({
  rating: 'ambitious',
  reason: null,
  current: 50,
  needed: 52.44,
  suggested: 2450,
  weeks: 10,
  prep_short: false,
  prep_weeks: 6,
  ...changes,
});

const race = (changes: Partial<Assessment> = {}): Goal =>
  goal({
    kind: 'race',
    discipline: 'running',
    distance_m: 10000,
    target_time_seconds: 2400,
    assessment: assessment(changes),
  });

describe('the words about how realistic a goal is', () => {
  it('name every rating', () => {
    expect(RATING_LABELS).toEqual({
      realistic: 'Realistic',
      ambitious: 'Ambitious',
      unrealistic: 'Unrealistic',
      unknown: 'Cannot be judged yet',
    });
  });

  it('say what to do for every reason', () => {
    expect(Object.keys(REASON_TEXTS).sort()).toEqual(
      ['no_date', 'no_form', 'no_model', 'no_target', 'out_of_range'].sort(),
    );
  });

  it.each([
    ['realistic', 'Within reach'],
    ['ambitious', 'A stretch'],
    ['unrealistic', 'Out of reach'],
  ] as const)('judges %s in a sentence', (rating, start) => {
    expect(judgementText(assessment({ rating })).startsWith(start)).toBe(true);
  });

  it('says why a goal could not be judged', () => {
    const unknown = assessment({ rating: 'unknown', reason: 'no_form' });

    expect(judgementText(unknown)).toBe(REASON_TEXTS.no_form);
  });
});

describe('figuresText', () => {
  it('tells the VDOT of a race with one decimal', () => {
    expect(figuresText(race())).toBe('Your running form: VDOT 50.0. The target needs VDOT 52.4.');
  });

  it('tells FTP in watts', () => {
    const ftp = goal({
      kind: 'threshold',
      metric: 'ftp',
      target_value: 300,
      assessment: assessment({ current: 240, needed: 300 }),
    });

    expect(figuresText(ftp)).toBe('Your FTP: 240 W. The target: 300 W.');
  });

  it('tells the threshold pace as minutes and seconds', () => {
    const pace = goal({
      kind: 'threshold',
      metric: 'threshold_pace',
      target_value: 270,
      assessment: assessment({ current: 300, needed: 270 }),
    });

    expect(figuresText(pace)).toBe('Your threshold pace: 5:00 /km. The target: 4:30 /km.');
  });

  it.each([
    ['no judgement', goal({})],
    ['no form', race({ current: null })],
    ['no target', race({ needed: null })],
  ])('is empty with %s', (_name, given) => {
    expect(figuresText(given)).toBe('');
  });
});

describe('the suggested target', () => {
  it('is a time for a race, as text and as it is typed', () => {
    expect(suggestedTarget(race())).toEqual({ text: '40:50', field: '40:50' });
    expect(suggestedTarget(race({ suggested: 12345 }))).toEqual({
      text: '3:25:45',
      field: '3:25:45',
    });
  });

  it('is a value for a threshold, as text and as it is typed', () => {
    const pace = goal({
      kind: 'threshold',
      metric: 'threshold_pace',
      assessment: assessment({ suggested: 286 }),
    });
    const ftp = goal({
      kind: 'threshold',
      metric: 'ftp',
      assessment: assessment({ suggested: 252 }),
    });

    expect(suggestedTarget(pace)).toEqual({ text: '4:46 /km', field: '4:46' });
    expect(suggestedTarget(ftp)).toEqual({ text: '252 W', field: '252' });
  });

  it.each(['realistic', 'unknown'] as const)('is none for a goal that is %s', (rating) => {
    expect(suggestedTarget(race({ rating }))).toBeNull();
  });

  it('is none without a suggestion or a judgement', () => {
    expect(suggestedTarget(race({ suggested: null }))).toBeNull();
    expect(suggestedTarget(goal({}))).toBeNull();
  });

  it('is said in a sentence', () => {
    expect(suggestionText(race())).toBe('A target that can be reached by then: 40:50.');
    expect(suggestionText(race({ rating: 'realistic' }))).toBe('');
  });
});

describe('preparationText', () => {
  it('warns when fewer weeks are left than the distance needs', () => {
    expect(preparationText(assessment({ prep_short: true, weeks: 3, prep_weeks: 6 }))).toBe(
      'Only 3 weeks are left; a race of this distance should have about 6 weeks of preparation.',
    );
  });

  it('says one week in the singular', () => {
    expect(preparationText(assessment({ prep_short: true, weeks: 1 }))).toContain(
      'Only 1 week is left',
    );
  });

  it('is empty when the preparation is long enough or unknown', () => {
    expect(preparationText(assessment())).toBe('');
    expect(preparationText(assessment({ prep_short: true, weeks: null }))).toBe('');
    expect(preparationText(assessment({ prep_short: true, prep_weeks: null }))).toBe('');
  });
});
