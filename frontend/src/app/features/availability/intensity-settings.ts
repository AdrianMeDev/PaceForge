import { Component, computed, input, model } from '@angular/core';
import {
  IntensityLevel,
  LimitName,
  Limits,
  OwnLimits,
} from '../../core/availability/availability-models';

/** The own limits as typed: empty means the level's value. */
export type OwnLimitTexts = Record<LimitName, string>;
/** Messages by field: the level and each own limit. */
export type IntensityErrors = Partial<Record<'intensity_level' | LimitName, string>>;
export type ReadOwnLimits = { ok: true; value: OwnLimits } | { ok: false; errors: IntensityErrors };

/** The names of the fields, in the order they are shown; also the names the server uses. */
export const LIMIT_NAMES: readonly LimitName[] = [
  'max_hard_days',
  'progression_warning_percent',
  'progression_error_percent',
  'easy_share_percent',
];
export const INTENSITY_FIELDS: readonly string[] = ['intensity_level', ...LIMIT_NAMES];

export const NO_OWN_LIMIT_TEXTS: OwnLimitTexts = {
  max_hard_days: '',
  progression_warning_percent: '',
  progression_error_percent: '',
  easy_share_percent: '',
};

const LEVELS: { value: IntensityLevel; label: string }[] = [
  { value: 'relaxed', label: 'Relaxed' },
  { value: 'normal', label: 'Normal' },
  { value: 'intensive', label: 'Intensive' },
];

/** The ranges the server accepts, both ends included. */
const RANGES: Record<LimitName, [number, number]> = {
  max_hard_days: [0, 4],
  progression_warning_percent: [100, 200],
  progression_error_percent: [100, 300],
  easy_share_percent: [50, 100],
};

const LABELS: Record<LimitName, string> = {
  max_hard_days: 'Hard days a week, at most',
  progression_warning_percent: 'Warning above (% of your usual week)',
  progression_error_percent: 'Error above (% of your usual week)',
  easy_share_percent: 'Easy share, at least (%)',
};

const WHOLE_NUMBER = /^\d+$/;

/** The same message the server gives for a value outside its range. */
function rangeMessage(name: LimitName): string {
  const [low, high] = RANGES[name];
  return name === 'max_hard_days'
    ? `Enter a whole number of days between ${low} and ${high}.`
    : `Enter a whole percent between ${low} and ${high}.`;
}

/**
 * The own limits as numbers (`null` for an empty field), or the messages by field. The checks are
 * those of the server: every value in its range, and the warning limit below the error limit,
 * also when one of them is the level's (the message then stands at the own one).
 */
export function readOwnLimits(texts: OwnLimitTexts, level: Limits): ReadOwnLimits {
  const own: Partial<OwnLimits> = {};
  const errors: IntensityErrors = {};
  for (const name of LIMIT_NAMES) {
    const text = texts[name].trim();
    if (text === '') {
      own[name] = null;
      continue;
    }
    const [low, high] = RANGES[name];
    const value = WHOLE_NUMBER.test(text) ? Number(text) : NaN;
    if (Number.isInteger(value) && value >= low && value <= high) {
      own[name] = value;
    } else {
      errors[name] = rangeMessage(name);
    }
  }
  if (Object.keys(errors).length) {
    return { ok: false, errors };
  }
  const limits = own as OwnLimits;
  const warning = limits.progression_warning_percent ?? level.progression_warning_percent;
  const error = limits.progression_error_percent ?? level.progression_error_percent;
  if (warning >= error) {
    const at =
      limits.progression_error_percent !== null
        ? 'progression_error_percent'
        : 'progression_warning_percent';
    return {
      ok: false,
      errors: {
        [at]: `The warning limit (${warning} %) must be below the error limit (${error} %).`,
      },
    };
  }
  return { ok: true, value: limits };
}

/** The own limits in the form people type them. */
export function ownLimitTexts(own: OwnLimits): OwnLimitTexts {
  const texts = { ...NO_OWN_LIMIT_TEXTS };
  for (const name of LIMIT_NAMES) {
    const value = own[name];
    texts[name] = value === null ? '' : String(value);
  }
  return texts;
}

/**
 * How hard plans may be: one of three levels, each with its limits of the planning rules, and
 * optionally an own value for each limit. A part of the availability form: the page holds the
 * values, checks them with `readOwnLimits` and saves them with everything else.
 */
@Component({
  selector: 'app-intensity-settings',
  templateUrl: './intensity-settings.html',
  styleUrl: './intensity-settings.css',
})
export class IntensitySettings {
  readonly level = model.required<IntensityLevel>();
  readonly own = model.required<OwnLimitTexts>();
  /** The limits of every level, as the server has them. */
  readonly levelLimits = input.required<Record<IntensityLevel, Limits>>();
  readonly errors = input<IntensityErrors>({});

  protected readonly levels = LEVELS;
  protected readonly names = LIMIT_NAMES;
  protected readonly labels = LABELS;

  /** The limits of the chosen level: what an empty field stands for. */
  protected readonly chosen = computed(() => this.levelLimits()[this.level()]);
  /** Own limits are shown open when there are any, or a message about one. */
  protected readonly hasOwn = computed(() =>
    LIMIT_NAMES.some((name) => this.own()[name] !== '' || this.errors()[name]),
  );

  protected describe(limits: Limits): string {
    const days = limits.max_hard_days === 1 ? '1 hard day' : `${limits.max_hard_days} hard days`;
    return (
      `${days} a week, at least ${limits.easy_share_percent} % easy; a warning above ` +
      `${limits.progression_warning_percent} % of your usual week, an error above ` +
      `${limits.progression_error_percent} %.`
    );
  }

  protected setOwn(name: LimitName, event: Event): void {
    const text = (event.target as HTMLInputElement).value;
    this.own.update((texts) => ({ ...texts, [name]: text }));
  }
}
