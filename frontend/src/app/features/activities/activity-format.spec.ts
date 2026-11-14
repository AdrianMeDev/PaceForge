import {
  MISSING,
  formatDistance,
  formatDuration,
  formatHeartRate,
  formatLoad,
  formatRpe,
  sourceLabel,
  sportLabel,
} from './activity-format';

describe('activity formatting', () => {
  describe('formatDuration', () => {
    it.each([
      [0, '0:00'],
      [59.4, '0:59'],
      [59.6, '1:00'],
      [3329, '55:29'],
      [3599.4, '59:59'],
      [3600, '1:00:00'],
      [3904.59, '1:05:05'],
      [86399, '23:59:59'],
      [90000, '25:00:00'],
    ])('shows %f seconds as %s', (seconds, text) => {
      expect(formatDuration(seconds)).toBe(text);
    });

    it('shows a dash for a duration the file does not report', () => {
      expect(formatDuration(null)).toBe(MISSING);
    });
  });

  describe('formatDistance', () => {
    it.each([
      [12766.23, '12.77 km'],
      [10398, '10.40 km'],
      [0, '0.00 km'],
      [999.4, '1.00 km'],
    ])('shows %f meters as %s', (meters, text) => {
      expect(formatDistance(meters)).toBe(text);
    });

    it('shows a dash for a distance the file does not report', () => {
      expect(formatDistance(null)).toBe(MISSING);
    });
  });

  it('shows heart rates with their unit, or a dash', () => {
    expect(formatHeartRate(155)).toBe('155 bpm');
    expect(formatHeartRate(null)).toBe(MISSING);
  });

  describe('sportLabel', () => {
    it.each([
      ['running', 'Running'],
      ['cycling', 'Cycling'],
      ['swimming', 'Swimming'],
      ['strength', 'Strength'],
    ] as const)('names %s', (sport, label) => {
      expect(sportLabel({ sport, source_sport: 'whatever' })).toBe(label);
    });

    it('adds the sport as the file calls it when it is not one of ours', () => {
      expect(sportLabel({ sport: 'other', source_sport: 'Rowing' })).toBe('Other (Rowing)');
    });

    it('does not add empty brackets', () => {
      expect(sportLabel({ sport: 'other', source_sport: '' })).toBe('Other');
    });
  });

  it('names the source formats', () => {
    expect(sourceLabel('fit_file')).toBe('FIT');
    expect(sourceLabel('tcx_file')).toBe('TCX');
  });

  describe('formatRpe and formatLoad', () => {
    it('shows the rating as it is and a dash for none', () => {
      expect(formatRpe(7)).toBe('7');
      expect(formatRpe(null)).toBe(MISSING);
    });

    it('shows the load in arbitrary units and a dash for none', () => {
      expect(formatLoad(315)).toBe('315 AU');
      expect(formatLoad(0)).toBe('0 AU');
      expect(formatLoad(null)).toBe(MISSING);
    });
  });

  describe('sourceLabel', () => {
    it('names a session entered by hand', () => {
      expect(sourceLabel('manual')).toBe('Entered by hand');
    });
  });
});
