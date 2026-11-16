import {
  BodyAndTraining,
  BodyChanges,
  Equipment,
  Sex,
  StrengthExperience,
  TrainingSport,
  TrainingYears,
} from '../../core/athlete/athlete-models';

/** The server's ranges for the body and training data (see `athletes/models.py`). */
export const BIRTH_YEAR_MIN = 1900;
/** The youngest athlete: the birth year cannot be later than this many years ago. */
export const MIN_AGE = 10;
export const WEIGHT_MIN = 25;
export const WEIGHT_MAX = 300;
export const RESTING_HR_MIN = 25;
export const RESTING_HR_MAX = 120;
export const TRAINING_YEARS_MAX = 80;

export const SEX_LABELS: Record<Sex, string> = {
  female: 'Female',
  male: 'Male',
  other: 'Other',
};

export const EXPERIENCE_LABELS: Record<StrengthExperience, string> = {
  beginner: 'Beginner',
  advanced: 'Advanced',
};

/** In the order the server stores them. */
export const EQUIPMENT_LABELS: Record<Equipment, string> = {
  gym: 'Gym',
  home: 'Bodyweight only',
  dumbbells: 'Dumbbells',
};

export const TRAINING_SPORT_LABELS: Record<TrainingSport, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength / gym',
};

/** What the user typed, as text; an empty text means "not said". */
export interface BodyDraft {
  birthYear: string;
  sex: Sex | '';
  weight: string;
  restingHr: string;
  years: Record<TrainingSport, string>;
  experience: StrengthExperience | '';
  equipment: Equipment[];
}

/** The messages by field of the form; a field without a message is fine. */
export type BodyErrors = Partial<Record<string, string>>;

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

/** A whole number from text, empty for `null`; a comma or a point is no whole number. */
export function parseWhole(
  text: string,
  low: number,
  high: number,
  message: string,
): Parsed<number | null> {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { ok: true, value: null };
  }
  if (!/^\d{1,5}$/.test(trimmed)) {
    return { ok: false, error: message };
  }
  const value = Number(trimmed);
  return value < low || value > high ? { ok: false, error: message } : { ok: true, value };
}

/** A weight in kilograms with at most one decimal (a comma works too), empty for `null`. */
export function parseWeight(text: string): Parsed<number | null> {
  const trimmed = text.trim();
  const message = `Enter a weight between ${WEIGHT_MIN} and ${WEIGHT_MAX} kg.`;
  if (trimmed === '') {
    return { ok: true, value: null };
  }
  if (!/^\d{1,3}([.,]\d)?$/.test(trimmed)) {
    return { ok: false, error: message };
  }
  const value = Number(trimmed.replace(',', '.'));
  return value < WEIGHT_MIN || value > WEIGHT_MAX
    ? { ok: false, error: message }
    : { ok: true, value };
}

/** The text of a number for a field; empty for `null`. */
export function numberText(value: number | null): string {
  return value === null ? '' : String(value);
}

/** The names of the fields as the server has them, which is also where their messages go. */
export const BODY_FIELDS = [
  'birth_year',
  'sex',
  'weight_kg',
  'resting_hr',
  'training_years',
  'strength_experience',
  'strength_equipment',
] as const;

/** The draft of what is stored. */
export function draftOf(data: BodyAndTraining): BodyDraft {
  return {
    birthYear: numberText(data.birth_year),
    sex: data.sex ?? '',
    weight: numberText(data.weight_kg),
    restingHr: numberText(data.resting_hr),
    years: {
      running: numberText(data.training_years.running),
      cycling: numberText(data.training_years.cycling),
      swimming: numberText(data.training_years.swimming),
      strength: numberText(data.training_years.strength),
    },
    experience: data.strength_experience ?? '',
    equipment: [...data.strength_equipment],
  };
}

/**
 * What to send for a draft, or the messages of the fields that cannot be used. Everything is
 * sent: an empty field clears the stored value.
 * @param thisYear the current year, which decides the latest birth year.
 */
export function changesOf(
  draft: BodyDraft,
  thisYear: number,
): { changes: BodyChanges } | { errors: BodyErrors } {
  const latest = thisYear - MIN_AGE;
  const errors: BodyErrors = {};
  const birth = parseWhole(
    draft.birthYear,
    BIRTH_YEAR_MIN,
    latest,
    `Enter a year between ${BIRTH_YEAR_MIN} and ${latest}.`,
  );
  const weight = parseWeight(draft.weight);
  const resting = parseWhole(
    draft.restingHr,
    RESTING_HR_MIN,
    RESTING_HR_MAX,
    `Enter a resting heart rate between ${RESTING_HR_MIN} and ${RESTING_HR_MAX} bpm.`,
  );
  const years: Partial<TrainingYears> = {};
  for (const sport of Object.keys(TRAINING_SPORT_LABELS) as TrainingSport[]) {
    const parsed = parseWhole(
      draft.years[sport],
      0,
      TRAINING_YEARS_MAX,
      `Enter whole years between 0 and ${TRAINING_YEARS_MAX}.`,
    );
    if (parsed.ok) {
      years[sport] = parsed.value;
    } else {
      errors['training_years'] = parsed.error;
    }
  }
  if (!birth.ok) {
    errors['birth_year'] = birth.error;
  }
  if (!weight.ok) {
    errors['weight_kg'] = weight.error;
  }
  if (!resting.ok) {
    errors['resting_hr'] = resting.error;
  }
  if (!birth.ok || !weight.ok || !resting.ok || Object.keys(errors).length) {
    return { errors };
  }
  return {
    changes: {
      birth_year: birth.value,
      sex: draft.sex || null,
      weight_kg: weight.value,
      resting_hr: resting.value,
      training_years: years,
      strength_experience: draft.experience || null,
      strength_equipment: draft.equipment,
    },
  };
}

/** Nothing entered. */
export function emptyDraft(): BodyDraft {
  return {
    birthYear: '',
    sex: '',
    weight: '',
    restingHr: '',
    years: { running: '', cycling: '', swimming: '', strength: '' },
    experience: '',
    equipment: [],
  };
}
