import { Zone } from '../../core/athlete/athlete-models';
import { describeZone, formatPace, formatValue, inputText, parseThreshold } from './athlete-format';

const zone = (lower: number | null, upper: number | null, unit: Zone['unit']): Zone => ({
  number: 1,
  name: 'x',
  lower,
  upper,
  unit,
});

describe('parseThreshold', () => {
  describe('numbers', () => {
    it.each([
      ['ftp', '250', 250],
      ['ftp', ' 250 ', 250],
      ['ftp', '250,5', 250.5],
      ['ftp', '250.5', 250.5],
      ['ftp', '30', 30],
      ['ftp', '2000', 2000],
      ['lthr', '165', 165],
      ['max_hr', '250', 250],
      ['max_hr', '30', 30],
    ] as const)('reads %s "%s" as %f', (metric, text, value) => {
      expect(parseThreshold(metric, text)).toEqual({ ok: true, value });
    });

    it.each(['', '   '])('asks for a value when the field is empty ("%s")', (text) => {
      expect(parseThreshold('ftp', text)).toEqual({ ok: false, error: 'Enter a value.' });
    });

    it.each(['abc', '25o', '-250', '+250', '2 50', '1e3', '.5', '5.', '0x10', '250 W', 'NaN', '∞'])(
      'does not read "%s" as a number',
      (text) => {
        expect(parseThreshold('ftp', text)).toEqual({
          ok: false,
          error: 'Enter a number, for example 250.',
        });
      },
    );

    it.each([
      ['ftp', '29', 'Enter a value between 30 and 2000 W.'],
      ['ftp', '2001', 'Enter a value between 30 and 2000 W.'],
      ['ftp', '0', 'Enter a value between 30 and 2000 W.'],
      ['lthr', '251', 'Enter a value between 30 and 250 bpm.'],
      ['lthr', '29,9', 'Enter a value between 30 and 250 bpm.'],
      ['max_hr', '300', 'Enter a value between 30 and 250 bpm.'],
    ] as const)('refuses %s "%s" as out of range', (metric, text, error) => {
      expect(parseThreshold(metric, text)).toEqual({ ok: false, error });
    });
  });

  describe('pace', () => {
    it.each([
      ['5:00', 300],
      ['4:59', 299],
      ['05:30', 330],
      ['2:00', 120],
      ['20:00', 1200],
      [' 6:05 ', 365],
    ])('reads "%s" as %i seconds per kilometre', (text, seconds) => {
      expect(parseThreshold('threshold_pace', text)).toEqual({ ok: true, value: seconds });
    });

    it.each([
      '300',
      '5.00',
      '5,00',
      '5:5',
      '5:60',
      '5:',
      ':30',
      '5:00:00',
      'fast',
      '-5:00',
      '5 : 00',
    ])('explains how to enter the pace when given "%s"', (text) => {
      expect(parseThreshold('threshold_pace', text)).toEqual({
        ok: false,
        error: 'Enter the pace as minutes and seconds per kilometre, for example 5:00.',
      });
    });

    it.each(['1:59', '0:30', '20:01', '59:59'])('refuses "%s" as out of range', (text) => {
      expect(parseThreshold('threshold_pace', text)).toEqual({
        ok: false,
        error: 'Enter a pace between 2:00 and 20:00 per km.',
      });
    });

    it('asks for a value when the field is empty', () => {
      expect(parseThreshold('threshold_pace', '')).toEqual({ ok: false, error: 'Enter a value.' });
    });
  });
});

describe('formatting', () => {
  it.each([
    [300, '5:00'],
    [299.4, '4:59'],
    [299.5, '5:00'],
    [305, '5:05'],
    [59, '0:59'],
    [3600, '60:00'],
  ])('shows %f seconds per kilometre as %s', (seconds, text) => {
    expect(formatPace(seconds)).toBe(text);
  });

  it.each([
    ['ftp', 250, '250 W'],
    ['ftp', 250.5, '251 W'],
    ['lthr', 165, '165 bpm'],
    ['max_hr', 189.4, '189 bpm'],
    ['threshold_pace', 300, '5:00 /km'],
  ] as const)('shows %s %f as "%s"', (metric, value, text) => {
    expect(formatValue(metric, value)).toBe(text);
  });

  it.each([
    ['ftp', 250, '250'],
    ['ftp', 250.5, '251'],
    ['max_hr', 190, '190'],
    ['threshold_pace', 300, '5:00'],
    ['threshold_pace', 365, '6:05'],
  ] as const)('puts %s %f into the field as "%s"', (metric, value, text) => {
    expect(inputText(metric, value)).toBe(text);
  });

  it('gives a value back that the input accepts', () => {
    for (const metric of ['ftp', 'lthr', 'max_hr', 'threshold_pace'] as const) {
      const value = metric === 'threshold_pace' ? 305 : 165;
      expect(parseThreshold(metric, inputText(metric, value))).toEqual({ ok: true, value });
    }
  });
});

describe('describeZone', () => {
  it.each([
    [zone(null, 138, 'W'), 'below 138 W'],
    [zone(138, 188, 'W'), '138–187 W'],
    [zone(375, null, 'W'), '375 W and above'],
    [zone(null, 140, 'bpm'), 'below 140 bpm'],
    [zone(149, 157, 'bpm'), '149–156 bpm'],
    [zone(165, null, 'bpm'), '165 bpm and above'],
  ])('describes %j as "%s"', (entry, text) => {
    expect(describeZone(entry)).toBe(text);
  });

  it.each([
    [zone(387, null, 's/km'), '6:27 /km or slower'],
    [zone(342, 387, 's/km'), '5:42–6:26 /km'],
    [zone(297, 318, 's/km'), '4:57–5:17 /km'],
    [zone(null, 297, 's/km'), 'faster than 4:57 /km'],
  ])('describes the pace zone %j as "%s"', (entry, text) => {
    expect(describeZone(entry)).toBe(text);
  });

  it('shows no gap and no overlap between neighbouring zones', () => {
    const upper = describeZone(zone(138, 188, 'W')); // 138–187
    const next = describeZone(zone(188, 225, 'W')); // 188–224

    expect(upper).toBe('138–187 W');
    expect(next).toBe('188–224 W');
  });
});
