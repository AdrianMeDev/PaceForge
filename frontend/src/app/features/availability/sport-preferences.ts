import { Component, input, model } from '@angular/core';
import {
  AvailabilitySport,
  SportPreferences,
  SportRole,
  StrengthFocus,
} from '../../core/availability/availability-models';

/** What the user typed or chose for one sport: empty means nothing said. */
export interface SportTexts {
  role: string;
  min: string;
  max: string;
}
export type PreferenceTexts = Record<AvailabilitySport, SportTexts>;
/** The whole form: every sport, and what strength training is for (empty: not said). */
export interface PreferenceForm {
  sports: PreferenceTexts;
  focus: string;
}
/** Messages by sport, from the form's own checks. */
export type PreferenceErrors = Partial<Record<AvailabilitySport, string>>;

export const SPORT_ORDER: readonly AvailabilitySport[] = [
  'running',
  'cycling',
  'swimming',
  'strength',
];
const SPORT_LABELS: Record<AvailabilitySport, string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength / gym',
};
const ROLES: { value: SportRole; label: string }[] = [
  { value: 'goal', label: 'Goal sport' },
  { value: 'secondary', label: 'Secondary sport' },
  { value: 'supplementary', label: 'Supplementary' },
];
const FOCUSES: { value: StrengthFocus; label: string }[] = [
  { value: 'legs', label: 'Legs' },
  { value: 'core', label: 'Core' },
  { value: 'upper_body', label: 'Upper body' },
  { value: 'full_body', label: 'Full body' },
];
/** The most sessions of a sport in a week: two a day. */
export const SESSIONS_MAX = 14;
export const SESSIONS_ERROR = `Enter whole numbers of sessions between 0 and ${SESSIONS_MAX}, the least not above the most.`;

export const NO_SPORT_TEXTS: SportTexts = { role: '', min: '', max: '' };
export const NO_PREFERENCE_FORM: PreferenceForm = {
  sports: {
    running: NO_SPORT_TEXTS,
    cycling: NO_SPORT_TEXTS,
    swimming: NO_SPORT_TEXTS,
    strength: NO_SPORT_TEXTS,
  },
  focus: '',
};

/** The form as the server has it, in the form people type it. */
export function preferenceForm(
  preferences: SportPreferences,
  focus: StrengthFocus | null,
): PreferenceForm {
  const sports = { ...NO_PREFERENCE_FORM.sports };
  for (const sport of SPORT_ORDER) {
    const one = preferences[sport];
    sports[sport] = {
      role: one.role ?? '',
      min: one.sessions_min === null ? '' : String(one.sessions_min),
      max: one.sessions_max === null ? '' : String(one.sessions_max),
    };
  }
  return { sports, focus: focus ?? '' };
}

/** `null` for an empty field, a whole number in range, `undefined` for anything else. */
function count(text: string): number | null | undefined {
  const typed = text.trim();
  if (typed === '') {
    return null;
  }
  const value = /^\d{1,2}$/.test(typed) ? Number(typed) : NaN;
  return value <= SESSIONS_MAX ? value : undefined;
}

/**
 * The form as the server takes it (all four sports, `null` for nothing said), or a message for
 * every sport whose numbers are unusable. The checks are the server's: whole numbers from 0 to
 * 14, the least not above the most.
 */
export function readPreferences(
  form: PreferenceForm,
):
  | { ok: true; preferences: SportPreferences; focus: StrengthFocus | null }
  | { ok: false; errors: PreferenceErrors } {
  const errors: PreferenceErrors = {};
  const preferences = {} as SportPreferences;
  for (const sport of SPORT_ORDER) {
    const texts = form.sports[sport];
    const low = count(texts.min);
    const high = count(texts.max);
    if (low === undefined || high === undefined || (low !== null && high !== null && low > high)) {
      errors[sport] = SESSIONS_ERROR;
      continue;
    }
    preferences[sport] = {
      role: (texts.role || null) as SportRole | null,
      sessions_min: low,
      sessions_max: high,
    };
  }
  if (Object.keys(errors).length) {
    return { ok: false, errors };
  }
  return { ok: true, preferences, focus: (form.focus || null) as StrengthFocus | null };
}

/**
 * What each sport is for the user (a role and how many sessions a week they want of it) and what
 * strength training is for. A part of the availability form: the page holds the values, checks
 * them with `readPreferences` and saves them with everything else.
 */
@Component({
  selector: 'app-sport-preferences',
  templateUrl: './sport-preferences.html',
  styleUrls: ['../auth/auth-form.css', './sport-preferences.css'],
})
export class SportPreferencesForm {
  readonly form = model.required<PreferenceForm>();
  /** The messages of the form's own checks, by sport. */
  readonly errors = input<PreferenceErrors>({});
  /** The server's message about the preferences or the focus as a whole. */
  readonly message = input<string | null>(null);

  protected readonly sports = SPORT_ORDER.map((value) => ({ value, label: SPORT_LABELS[value] }));
  protected readonly roles = ROLES;
  protected readonly focuses = FOCUSES;

  protected set(sport: AvailabilitySport, name: keyof SportTexts, event: Event): void {
    const text = (event.target as HTMLInputElement | HTMLSelectElement).value;
    this.form.update((old) => ({
      ...old,
      sports: { ...old.sports, [sport]: { ...old.sports[sport], [name]: text } },
    }));
  }

  protected setFocus(event: Event): void {
    const text = (event.target as HTMLSelectElement).value;
    this.form.update((old) => ({ ...old, focus: text }));
  }
}
