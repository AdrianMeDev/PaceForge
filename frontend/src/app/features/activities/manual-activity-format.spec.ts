import {
  DISTANCE_MAX_KM,
  DURATION_MAX_MINUTES,
  RPE_CHOICES,
  SPORT_CHOICES,
  parseDistance,
  parseDuration,
  timeText,
  todayText,
} from './manual-activity-format';

describe('parseDuration', () => {
  it.each([
    ['1', 1],
    ['45', 45],
    [' 90 ', 90],
    ['1440', 1440],
    ['007', 7],
  ])('reads "%s" as %i minutes', (text, minutes) => {
    expect(parseDuration(text)).toEqual({ ok: true, value: minutes });
  });

  it.each([
    '',
    '   ',
    '0',
    '1441',
    '-5',
    '1.5',
    '1,5',
    '1:30',
    'abc',
    '45min',
    '1e2',
    '99999999999999999999',
  ])('refuses "%s" with a message', (text) => {
    const result = parseDuration(text);
    expect(result.ok).toBe(false);
    expect(result.ok ? '' : result.error).not.toBe('');
  });

  it('names the limit in the message', () => {
    const result = parseDuration('1441');
    expect(result).toEqual({
      ok: false,
      error: `Enter whole minutes from 1 to ${DURATION_MAX_MINUTES}.`,
    });
  });
});

describe('parseDistance', () => {
  it.each([
    ['', null],
    ['  ', null],
    ['0', 0],
    ['5', 5],
    ['5.5', 5.5],
    ['5,5', 5.5],
    ['1000', 1000],
    ['12.345', 12.345],
  ])('reads "%s" as %s', (text, km) => {
    expect(parseDistance(text)).toEqual({ ok: true, value: km });
  });

  it.each(['-1', '1000.5', '1001', 'abc', '5 km', '5.', '.5', '1.2345', '1e3', '5,5,5'])(
    'refuses "%s" with a message',
    (text) => {
      const result = parseDistance(text);
      expect(result.ok).toBe(false);
      expect(result.ok ? '' : result.error).toContain(`${DISTANCE_MAX_KM}`);
    },
  );
});

describe('the clock of the user', () => {
  it('writes the day with the zeros of a date', () => {
    expect(todayText(new Date(2026, 0, 5, 3, 4))).toBe('2026-01-05');
    expect(todayText(new Date(2026, 10, 12, 23, 59))).toBe('2026-11-12');
  });

  it('writes the time with the zeros of a clock', () => {
    expect(timeText(new Date(2026, 0, 5, 3, 4))).toBe('03:04');
    expect(timeText(new Date(2026, 10, 12, 23, 59))).toBe('23:59');
    expect(timeText(new Date(2026, 10, 12, 0, 0))).toBe('00:00');
  });
});

describe('the choices', () => {
  it('has the five sports of an activity', () => {
    expect(SPORT_CHOICES.map((choice) => choice.value)).toEqual([
      'running',
      'cycling',
      'swimming',
      'strength',
      'other',
    ]);
  });

  it('has the ratings 1 to 10, each with its number in the text', () => {
    expect(RPE_CHOICES.map((choice) => choice.value)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    for (const choice of RPE_CHOICES) {
      expect(choice.label.startsWith(`${choice.value} – `)).toBe(true);
    }
  });
});
