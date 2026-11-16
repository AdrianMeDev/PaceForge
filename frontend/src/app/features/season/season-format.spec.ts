import { SeasonRace } from '../../core/season/season-models';
import {
  FOCUS_LABELS,
  KIND_LABELS,
  PHASE_HINTS,
  PHASE_LABELS,
  PRIORITY_LETTERS,
  keySessionText,
  minutesBySport,
  raceText,
  usedShare,
} from './season-format';

const RACE: SeasonRace = {
  date: '2027-02-28',
  priority: 'main',
  discipline: 'running',
  distance_m: 42195,
  title: 'Berlin Marathon',
};

describe('the labels', () => {
  it('name every phase and say what it is for', () => {
    expect(PHASE_LABELS).toEqual({
      base: 'Base',
      build: 'Build',
      specific: 'Specific',
      taper: 'Taper',
      transition: 'Transition',
    });
    expect(Object.keys(PHASE_HINTS)).toEqual(Object.keys(PHASE_LABELS));
    expect(Object.values(PHASE_HINTS).every((hint) => hint.endsWith('.'))).toBe(true);
  });

  it('give A, B and C to the priorities', () => {
    expect(PRIORITY_LETTERS).toEqual({ main: 'A', secondary: 'B', preparation: 'C' });
  });
});

describe('raceText', () => {
  it('writes the letter, the title and the distance', () => {
    expect(raceText(RACE)).toBe('A · Berlin Marathon · 42.2 km');
  });

  it('leaves the distance out if there is none', () => {
    expect(raceText({ ...RACE, priority: 'secondary', distance_m: null })).toBe(
      'B · Berlin Marathon',
    );
  });

  it('writes a short distance in metres and a C race with its letter', () => {
    expect(raceText({ ...RACE, priority: 'preparation', distance_m: 800 })).toBe(
      'C · Berlin Marathon · 800 m',
    );
  });
});

describe('usedShare', () => {
  it('is the share of the time on offer that is planned', () => {
    expect(usedShare(150, 300)).toBe('50 %');
    expect(usedShare(300, 300)).toBe('100 %');
    expect(usedShare(100, 300)).toBe('33 %');
  });

  it('is empty for a week that offers nothing', () => {
    expect(usedShare(0, 0)).toBe('');
  });
});

describe('the words of a filled season', () => {
  it('name every focus and kind of session', () => {
    expect(Object.keys(FOCUS_LABELS)).toEqual([
      'recovery',
      'endurance',
      'tempo',
      'threshold',
      'vo2max',
      'race_specific',
    ]);
    expect(Object.keys(KIND_LABELS)).toEqual([
      'long',
      'tempo',
      'threshold',
      'vo2max',
      'race_pace',
      'strength',
      'race',
    ]);
  });

  it('tell the minutes of each sport in a fixed order and leave out what is not planned', () => {
    expect(minutesBySport({ cycling: 90, running: 180, swimming: 0 })).toBe(
      'Running 3 h · Cycling 1 h 30 min',
    );
    expect(minutesBySport({})).toBe('');
  });

  it('tell a key session in a line, with its detail only if there is one', () => {
    expect(keySessionText({ sport: 'running', kind: 'long', minutes: 90, detail: '' })).toBe(
      'Running · Long · 1 h 30 min',
    );
    expect(
      keySessionText({ sport: 'cycling', kind: 'threshold', minutes: 60, detail: '3 x 10 min' }),
    ).toBe('Cycling · Threshold · 1 h · 3 x 10 min');
  });
});
