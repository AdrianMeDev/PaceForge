import { BestTime } from '../../core/athlete/athlete-models';
import {
  DISTANCES,
  DISTANCE_LABELS,
  EARLIEST_DAY,
  draftOf,
  inputOf,
  standing,
  todayText,
} from './best-times-format';

const TODAY = '2026-11-16';

const stored = (changes: Partial<BestTime> = {}): BestTime => ({
  seconds: 1197,
  date: '2026-10-03',
  vdot: 50,
  recent: true,
  counts: true,
  ...changes,
});

describe('the distances', () => {
  it('are listed from the shortest and named in words', () => {
    expect(DISTANCES).toEqual(['5k', '10k', 'half_marathon', 'marathon']);
    expect(DISTANCE_LABELS).toEqual({
      '5k': '5 km',
      '10k': '10 km',
      half_marathon: 'Half marathon',
      marathon: 'Marathon',
    });
  });
});

describe('draftOf', () => {
  it('is empty for no time', () => {
    expect(draftOf(null)).toEqual({ time: '', date: '' });
  });

  it('shows the time as minutes and seconds or hours, minutes and seconds', () => {
    expect(draftOf(stored())).toEqual({ time: '19:57', date: '2026-10-03' });
    expect(draftOf(stored({ seconds: 11449 }))).toEqual({ time: '3:10:49', date: '2026-10-03' });
  });
});

describe('inputOf', () => {
  it.each([
    ['19:57', 1197],
    [' 19:57 ', 1197],
    ['1:35:00', 5700],
    ['3:10:49', 11449],
  ])('reads the time "%s" as %i seconds', (time, seconds) => {
    expect(inputOf({ time, date: '2026-10-03' }, TODAY)).toEqual({
      ok: true,
      value: { seconds, date: '2026-10-03' },
    });
  });

  it('takes today and the first day', () => {
    expect(inputOf({ time: '19:57', date: TODAY }, TODAY).ok).toBe(true);
    expect(inputOf({ time: '19:57', date: EARLIEST_DAY }, TODAY).ok).toBe(true);
  });

  it.each(['', '   '])('asks for a time when the field says "%s"', (time) => {
    expect(inputOf({ time, date: '2026-10-03' }, TODAY)).toEqual({
      ok: false,
      errors: { seconds: 'Enter your time, for example 19:57 or 1:35:00.' },
    });
  });

  it.each(['abc', '1957', '19:5', '19:99', '1:70:00', '19.57'])(
    'refuses the time "%s" and says how to write one',
    (time) => {
      const result = inputOf({ time, date: '2026-10-03' }, TODAY);

      expect(result.ok).toBe(false);
      expect('errors' in result && Object.keys(result.errors)).toEqual(['seconds']);
    },
  );

  it.each(['', 'soon', '03.10.2026', '2026-13-45', '2026-10-3'])(
    'asks for the day when the field says "%s"',
    (date) => {
      expect(inputOf({ time: '19:57', date }, TODAY)).toEqual({
        ok: false,
        errors: { date: 'Enter the day of the race.' },
      });
    },
  );

  it.each(['2026-11-17', '1899-12-31'])('refuses the day %s', (date) => {
    expect(inputOf({ time: '19:57', date }, TODAY)).toEqual({
      ok: false,
      errors: { date: 'Enter the day of the race: not in the future, not before 1900.' },
    });
  });

  it('names both fields when both are wrong', () => {
    const result = inputOf({ time: '', date: '' }, TODAY);

    expect('errors' in result && Object.keys(result.errors)).toEqual(['seconds', 'date']);
  });
});

describe('todayText', () => {
  it('writes the day with two digits for month and day', () => {
    expect(todayText(new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(todayText(new Date(2026, 10, 16))).toBe('2026-11-16');
  });
});

describe('standing', () => {
  it('says which time gives the pace', () => {
    expect(standing(stored())).toBe('This one gives your threshold pace.');
  });

  it('says when a newer race does', () => {
    expect(standing(stored({ counts: false }))).toBe('A newer race gives your threshold pace.');
  });

  it('says when the race is too old', () => {
    expect(standing(stored({ counts: false, recent: false }))).toBe(
      'More than a year ago: too old to count.',
    );
  });
});
