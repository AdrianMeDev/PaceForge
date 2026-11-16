import {
  BIRTH_YEAR_MIN,
  BodyDraft,
  RESTING_HR_MAX,
  RESTING_HR_MIN,
  TRAINING_YEARS_MAX,
  WEIGHT_MAX,
  WEIGHT_MIN,
  changesOf,
  draftOf,
  emptyDraft,
  numberText,
  parseWeight,
  parseWhole,
} from './body-data-format';

const YEAR = 2026;

function draft(changes: Partial<BodyDraft> = {}): BodyDraft {
  return { ...emptyDraft(), ...changes };
}

describe('parseWhole', () => {
  const MESSAGE = 'nope';

  it.each([
    ['', null],
    ['   ', null],
    ['5', 5],
    [' 12 ', 12],
    ['0', 0],
    ['80', 80],
  ])('reads "%s" as %j', (text, value) => {
    expect(parseWhole(text, 0, 80, MESSAGE)).toEqual({ ok: true, value });
  });

  it.each(['81', '-1', '1.5', '1,5', 'abc', '5 0', '1e1', '+5', '123456', '٣'])(
    'refuses "%s"',
    (text) => {
      expect(parseWhole(text, 0, 80, MESSAGE)).toEqual({ ok: false, error: MESSAGE });
    },
  );
});

describe('parseWeight', () => {
  it.each([
    ['', null],
    ['61', 61],
    ['61.5', 61.5],
    ['61,5', 61.5],
    [String(WEIGHT_MIN), WEIGHT_MIN],
    [String(WEIGHT_MAX), WEIGHT_MAX],
  ])('reads "%s" as %j', (text, value) => {
    expect(parseWeight(text)).toEqual({ ok: true, value });
  });

  it.each(['24.9', '300.1', '61.55', '61.', '.5', 'abc', '-61', '1e2', '6 1'])(
    'refuses "%s" and names the range',
    (text) => {
      expect(parseWeight(text)).toEqual({
        ok: false,
        error: 'Enter a weight between 25 and 300 kg.',
      });
    },
  );
});

describe('numberText', () => {
  it('is empty for nothing and the number otherwise', () => {
    expect(numberText(null)).toBe('');
    expect(numberText(0)).toBe('0');
    expect(numberText(61.5)).toBe('61.5');
  });
});

describe('draftOf', () => {
  it('turns what is stored into text', () => {
    expect(
      draftOf({
        birth_year: 1985,
        sex: 'female',
        weight_kg: 61.5,
        resting_hr: 48,
        training_years: { running: 12, cycling: null, swimming: 0, strength: 1 },
        strength_experience: 'beginner',
        strength_equipment: ['gym', 'home'],
      }),
    ).toEqual({
      birthYear: '1985',
      sex: 'female',
      weight: '61.5',
      restingHr: '48',
      years: { running: '12', cycling: '', swimming: '0', strength: '1' },
      experience: 'beginner',
      equipment: ['gym', 'home'],
    });
  });

  it('turns nothing into an empty draft', () => {
    expect(
      draftOf({
        birth_year: null,
        sex: null,
        weight_kg: null,
        resting_hr: null,
        training_years: { running: null, cycling: null, swimming: null, strength: null },
        strength_experience: null,
        strength_equipment: [],
      }),
    ).toEqual(emptyDraft());
  });

  it('copies the equipment', () => {
    const equipment = ['gym' as const];

    const result = draftOf({ ...nothing(), strength_equipment: equipment });

    expect(result.equipment).toEqual(equipment);
    expect(result.equipment).not.toBe(equipment);
  });
});

function nothing() {
  return {
    birth_year: null,
    sex: null,
    weight_kg: null,
    resting_hr: null,
    training_years: { running: null, cycling: null, swimming: null, strength: null },
    strength_experience: null,
    strength_equipment: [],
  };
}

describe('changesOf', () => {
  it('sends every field, null for what is empty', () => {
    expect(changesOf(draft(), YEAR)).toEqual({
      changes: {
        birth_year: null,
        sex: null,
        weight_kg: null,
        resting_hr: null,
        training_years: { running: null, cycling: null, swimming: null, strength: null },
        strength_experience: null,
        strength_equipment: [],
      },
    });
  });

  it('turns a full draft into numbers and fixed words', () => {
    const full = draft({
      birthYear: '1985',
      sex: 'male',
      weight: '70,5',
      restingHr: '50',
      years: { running: '12', cycling: '3', swimming: '0', strength: '' },
      experience: 'advanced',
      equipment: ['dumbbells', 'gym'],
    });

    expect(changesOf(full, YEAR)).toEqual({
      changes: {
        birth_year: 1985,
        sex: 'male',
        weight_kg: 70.5,
        resting_hr: 50,
        training_years: { running: 12, cycling: 3, swimming: 0, strength: null },
        strength_experience: 'advanced',
        strength_equipment: ['dumbbells', 'gym'],
      },
    });
  });

  it('accepts the ends of the ranges, the latest birth year being ten years ago', () => {
    const ends = draft({
      birthYear: String(YEAR - 10),
      weight: String(WEIGHT_MAX),
      restingHr: String(RESTING_HR_MIN),
      years: { running: String(TRAINING_YEARS_MAX), cycling: '0', swimming: '', strength: '' },
    });

    expect('changes' in changesOf(ends, YEAR)).toBe(true);
    expect('changes' in changesOf(draft({ birthYear: String(BIRTH_YEAR_MIN) }), YEAR)).toBe(true);
    expect('changes' in changesOf(draft({ restingHr: String(RESTING_HR_MAX) }), YEAR)).toBe(true);
  });

  it('names the birth years that are too early or too late', () => {
    const latest = YEAR - 10;

    expect(changesOf(draft({ birthYear: String(BIRTH_YEAR_MIN - 1) }), YEAR)).toEqual({
      errors: { birth_year: `Enter a year between 1900 and ${latest}.` },
    });
    expect(changesOf(draft({ birthYear: String(latest + 1) }), YEAR)).toEqual({
      errors: { birth_year: `Enter a year between 1900 and ${latest}.` },
    });
  });

  it('names every field that cannot be used, once', () => {
    const bad = draft({
      birthYear: 'x',
      weight: '5',
      restingHr: '5',
      years: { running: '81', cycling: 'x', swimming: '', strength: '' },
    });

    expect(changesOf(bad, YEAR)).toEqual({
      errors: {
        birth_year: 'Enter a year between 1900 and 2016.',
        weight_kg: 'Enter a weight between 25 and 300 kg.',
        resting_hr: 'Enter a resting heart rate between 25 and 120 bpm.',
        training_years: 'Enter whole years between 0 and 80.',
      },
    });
  });
});
