import {
  DAY_MAX_MINUTES,
  WEEKDAY_NAMES,
  WEEK_MAX_MINUTES,
  formatMinutes,
  parseMinutes,
} from './availability-format';

describe('formatMinutes', () => {
  it.each([
    [0, '0:00'],
    [5, '0:05'],
    [59, '0:59'],
    [60, '1:00'],
    [90, '1:30'],
    [605, '10:05'],
    [1440, '24:00'],
    [10080, '168:00'],
  ])('shows %i minutes as %s', (minutes, text) => {
    expect(formatMinutes(minutes)).toBe(text);
  });
});

describe('parseMinutes', () => {
  it.each([
    ['0', 0],
    ['90', 90],
    ['090', 90],
    [' 45 ', 45],
    ['1440', 1440],
    ['0:00', 0],
    ['1:30', 90],
    ['01:30', 90],
    ['0:59', 59],
    ['24:00', 1440],
    [' 2:15 ', 135],
  ])('reads "%s" as %i minutes', (text, minutes) => {
    expect(parseMinutes(text, DAY_MAX_MINUTES)).toEqual({ ok: true, value: minutes });
  });

  it.each([
    ['', 'nothing'],
    ['  ', 'only spaces'],
    ['abc', 'text'],
    ['1:5', 'minutes with one digit'],
    ['1:60', 'sixty minutes'],
    ['1:75', 'seventy-five minutes'],
    [':30', 'no hours'],
    ['1:', 'no minutes'],
    ['1:30:00', 'seconds'],
    ['1,5', 'a decimal comma'],
    ['1.5', 'a decimal point'],
    ['-30', 'a negative number'],
    ['+30', 'a sign'],
    ['1e2', 'an exponent'],
    ['90 min', 'a unit'],
    ['1h30', 'letters between'],
    ['1 30', 'a space between'],
    ['1234:00', 'four digits of hours'],
    ['123456', 'six digits of minutes'],
  ])('does not read "%s" (%s)', (text) => {
    expect(parseMinutes(text, WEEK_MAX_MINUTES)).toEqual({
      ok: false,
      error: 'Enter minutes (90) or hours and minutes (1:30).',
    });
  });

  it.each(['1441', '24:01', '25:00', '99999'])('refuses "%s" for a day as too long', (text) => {
    expect(parseMinutes(text, DAY_MAX_MINUTES)).toEqual({
      ok: false,
      error: 'Enter at most 24:00 (1440 minutes).',
    });
  });

  it('takes more for a week and says what the limit is', () => {
    expect(parseMinutes('168:00', WEEK_MAX_MINUTES)).toEqual({ ok: true, value: 10080 });
    expect(parseMinutes('10080', WEEK_MAX_MINUTES)).toEqual({ ok: true, value: 10080 });
    expect(parseMinutes('168:01', WEEK_MAX_MINUTES)).toEqual({
      ok: false,
      error: 'Enter at most 168:00 (10080 minutes).',
    });
    expect(parseMinutes('10081', WEEK_MAX_MINUTES)).toMatchObject({ ok: false });
  });

  it('gives back what the page shows', () => {
    for (const minutes of [0, 1, 59, 60, 90, 605, 1439, 1440]) {
      expect(parseMinutes(formatMinutes(minutes), DAY_MAX_MINUTES)).toEqual({
        ok: true,
        value: minutes,
      });
    }
    expect(parseMinutes(formatMinutes(10080), WEEK_MAX_MINUTES)).toEqual({
      ok: true,
      value: 10080,
    });
  });
});

describe('the limits and names', () => {
  it('are written out on purpose', () => {
    expect(DAY_MAX_MINUTES).toBe(1440);
    expect(WEEK_MAX_MINUTES).toBe(10080);
    expect([...WEEKDAY_NAMES]).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ]);
  });
});
