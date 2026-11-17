import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AvailabilityApi } from '../../core/availability/availability-api';
import { CoachApi } from '../../core/coach/coach-api';
import {
  Availability,
  AvailabilityChanges,
  AvailabilitySlot,
  AvailabilitySport,
  IntensityLevel,
  Limits,
  OwnLimits,
} from '../../core/availability/availability-models';
import {
  DAY_MAX_MINUTES,
  WEEKDAY_NAMES,
  WEEK_MAX_MINUTES,
  formatMinutes,
  parseMinutes,
} from './availability-format';
import { Parsed } from '../goals/goal-format';
import { DayOptions, EVERY_DAY_DOUBLE, EVERY_DAY_OPEN, windowErrors } from './day-options';
import {
  INTENSITY_FIELDS,
  IntensityErrors,
  IntensitySettings,
  LIMIT_NAMES,
  NO_OWN_LIMIT_TEXTS,
  OwnLimitTexts,
  ownLimitTexts,
  readOwnLimits,
} from './intensity-settings';
import { FixedSessionsPanel } from './fixed-sessions-panel';
import { LimitationsPanel } from './limitations-panel';
import {
  NO_PREFERENCE_FORM,
  PreferenceErrors,
  PreferenceForm,
  SportPreferencesForm,
  preferenceForm,
  readPreferences,
} from './sport-preferences';
import {
  NO_WISH_TEXTS,
  WISH_FIELDS,
  WeekWishes,
  WishErrors,
  WishTexts,
  readWishes,
} from './week-wishes';
import { PageHeader } from '../../shared/page-header';
import { PeriodsPanel } from './periods-panel';
import { UNKNOWN_PROVIDER, providerLine } from './provider-line';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const FALLBACK = 'Something went wrong. Please try again.';
const LIMITATIONS_MAX = 1000;
/** How much of the free text goes to the coach if the user allows it (see the briefing). */
export const LIMITATIONS_TEXT_TOLD = 150;
const DAYS = [0, 1, 2, 3, 4, 5, 6];
/** The sports to tick, in the order the server keeps them. */
const SPORT_CHOICES: { value: AvailabilitySport; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'cycling', label: 'Cycling' },
  { value: 'swimming', label: 'Swimming' },
  { value: 'strength', label: 'Strength / gym' },
];
const NO_SPORT = 'Choose at least one sport.';
const NO_ERRORS: (string | null)[] = DAYS.map(() => null);

/** A number as the text of a form field, empty for none. */
function numberText(value: number | null): string {
  return value === null ? '' : String(value);
}

/** A day field: empty means no time. */
function dayMinutes(text: string): Parsed<number> {
  return text.trim() === '' ? { ok: true, value: 0 } : parseMinutes(text, DAY_MAX_MINUTES);
}

/**
 * How much time the user can train: minutes per weekday, an optional weekly budget that caps what
 * the days add up to, optionally what a normal week of training is for them (a reference for the
 * planning after a break, no limit), the sports they want in a plan, whether stretching may be
 * added to sessions, limitations as free text, and how hard plans may be (an intensity level with
 * optional own limits). Everything is saved together with one Save.
 * What is checked here is what the server checks too, so that the message appears next to the
 * field; the server's own messages are shown the same way.
 */
@Component({
  selector: 'app-availability-page',
  imports: [
    RouterLink,
    PageHeader,
    PeriodsPanel,
    FixedSessionsPanel,
    LimitationsPanel,
    IntensitySettings,
    DayOptions,
    WeekWishes,
    SportPreferencesForm,
  ],
  templateUrl: './availability-page.html',
  styleUrl: './availability-page.css',
})
export class AvailabilityPage implements OnInit {
  private readonly api = inject(AvailabilityApi);
  private readonly coach = inject(CoachApi);

  protected readonly view = signal<View>('loading');
  /** What is in the seven day fields, Monday first. */
  protected readonly days = signal<string[]>(DAYS.map(() => ''));
  protected readonly budget = signal('');
  protected readonly typical = signal('');
  /** The sports that are ticked. */
  protected readonly sports = signal<AvailabilitySport[]>(
    SPORT_CHOICES.map((sport) => sport.value),
  );
  protected readonly stretching = signal(false);
  protected readonly limitations = signal('');
  protected readonly shareText = signal(false);
  protected readonly preferences = signal<PreferenceForm>(NO_PREFERENCE_FORM);
  protected readonly preferenceErrors = signal<PreferenceErrors>({});
  /** The server's message about the preferences or the focus as a whole. */
  protected readonly preferencesError = signal<string | null>(null);
  protected readonly wishes = signal<WishTexts>(NO_WISH_TEXTS);
  protected readonly wishErrors = signal<WishErrors>({});
  protected readonly intensityLevel = signal<IntensityLevel>('normal');
  protected readonly ownLimits = signal<OwnLimitTexts>(NO_OWN_LIMIT_TEXTS);
  /** The limits of every level as the server has them; set with the first answer. */
  protected readonly levelLimits = signal<Record<IntensityLevel, Limits> | null>(null);
  protected readonly intensityErrors = signal<IntensityErrors>({});
  /** Where what the user lets go to the AI coach goes, in a few words. */
  protected readonly provider = signal(UNKNOWN_PROVIDER);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly dayErrors = signal<(string | null)[]>(NO_ERRORS);
  protected readonly weekdaysError = signal<string | null>(null);
  protected readonly doubleDays = signal<boolean[]>(EVERY_DAY_DOUBLE);
  protected readonly timeWindows = signal<AvailabilitySlot[][]>(EVERY_DAY_OPEN);
  /** A message for each weekday that has no part of the day, from the form. */
  protected readonly windowErrors = signal<(string | null)[]>(NO_ERRORS);
  /** The server's message about the double days or the time windows as a whole. */
  protected readonly dayOptionsError = signal<string | null>(null);
  protected readonly budgetError = signal<string | null>(null);
  protected readonly typicalError = signal<string | null>(null);
  protected readonly sportsError = signal<string | null>(null);
  protected readonly stretchingError = signal<string | null>(null);
  protected readonly limitationsError = signal<string | null>(null);
  protected readonly shareTextError = signal<string | null>(null);
  protected readonly textTold = LIMITATIONS_TEXT_TOLD;

  protected readonly sportChoices = SPORT_CHOICES;
  protected readonly names = WEEKDAY_NAMES;
  protected readonly indexes = DAYS;

  /** The days added up; `null` while a field is not a usable time. */
  protected readonly total = computed(() => {
    let sum = 0;
    for (const text of this.days()) {
      const minutes = dayMinutes(text);
      if (!minutes.ok) {
        return null;
      }
      sum += minutes.value;
    }
    return sum;
  });
  /** The line under the title: what the days add up to. */
  protected readonly subtitle = computed(() => {
    const sum = this.totalText();
    return this.view() === 'ready' && sum ? `${sum} per week` : '';
  });
  protected readonly totalText = computed(() => {
    const total = this.total();
    return total === null ? '' : formatMinutes(total);
  });
  /** Said when the budget is below the sum: that is allowed, and here is what it means. */
  protected readonly capNote = computed(() => {
    const total = this.total();
    const text = this.budget().trim();
    const budget = text === '' ? null : parseMinutes(text, WEEK_MAX_MINUTES);
    if (total === null || budget === null || !budget.ok || budget.value >= total) {
      return '';
    }
    return `Your weekly budget (${formatMinutes(budget.value)}) is lower than the sum of the days, so a week offers at most ${formatMinutes(budget.value)}.`;
  });

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.get();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.show(result.availability);
      this.view.set('ready');
      void this.loadProvider();
    } catch {
      this.view.set('unreachable');
    }
  }

  /** The provider is only named in hints: if it cannot be read, the hints say so in general. */
  private async loadProvider(): Promise<void> {
    try {
      const result = await this.coach.get();
      this.provider.set(providerLine(result.kind === 'ok' ? result.state : null));
    } catch {
      this.provider.set(UNKNOWN_PROVIDER);
    }
  }

  /** The periods panel found the session gone. */
  protected endSession(): void {
    this.view.set('signed_out');
  }

  protected read(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  protected isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  protected setSport(sport: AvailabilitySport, ticked: boolean): void {
    this.sports.update((list) => {
      const rest = list.filter((candidate) => candidate !== sport);
      return ticked ? [...rest, sport] : rest;
    });
  }

  protected setDay(index: number, text: string): void {
    this.days.update((list) => list.map((old, i) => (i === index ? text : old)));
  }

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    this.errors.set([]);
    this.notice.set(null);
    const changes = this.build();
    if (changes === null) {
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.api.save(changes);
      switch (result.kind) {
        case 'ok':
          this.show(result.availability);
          this.notice.set('Your training time was saved.');
          break;
        case 'invalid':
          this.showServerMessages(result.fields, result.errors);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** The request for what is in the form, or `null` (with the messages set) if it is unusable. */
  private build(): AvailabilityChanges | null {
    let usable = true;
    const weekdays: number[] = [];
    const dayErrors: (string | null)[] = [];
    for (const text of this.days()) {
      const minutes = dayMinutes(text);
      weekdays.push(minutes.ok ? minutes.value : 0);
      dayErrors.push(minutes.ok ? null : minutes.error);
      usable &&= minutes.ok;
    }
    this.dayErrors.set(dayErrors);
    this.weekdaysError.set(null);

    const windows = windowErrors(this.timeWindows());
    this.windowErrors.set(windows);
    this.dayOptionsError.set(null);
    usable &&= windows.every((message) => message === null);

    let weeklyBudget: number | null = null;
    const budgetText = this.budget().trim();
    const budget = budgetText === '' ? null : parseMinutes(budgetText, WEEK_MAX_MINUTES);
    if (budget === null) {
      this.budgetError.set(null);
    } else if (budget.ok) {
      weeklyBudget = budget.value;
      this.budgetError.set(null);
    } else {
      this.budgetError.set(budget.error);
      usable = false;
    }

    const preference = readPreferences(this.preferences());
    let preferenceValues: Partial<AvailabilityChanges> = {};
    if (preference.ok) {
      preferenceValues = {
        sport_preferences: preference.preferences,
        strength_focus: preference.focus,
      };
      this.preferenceErrors.set({});
    } else {
      this.preferenceErrors.set(preference.errors);
      usable = false;
    }
    this.preferencesError.set(null);

    const read = readWishes(this.wishes(), weeklyBudget);
    let wishValues: Partial<AvailabilityChanges> = {};
    if (read.ok) {
      wishValues = read.value;
      this.wishErrors.set({});
    } else {
      this.wishErrors.set(read.errors);
      usable = false;
    }

    let typicalWeek: number | null = null;
    const typicalText = this.typical().trim();
    const typical = typicalText === '' ? null : parseMinutes(typicalText, WEEK_MAX_MINUTES);
    if (typical === null) {
      this.typicalError.set(null);
    } else if (typical.ok) {
      typicalWeek = typical.value;
      this.typicalError.set(null);
    } else {
      this.typicalError.set(typical.error);
      usable = false;
    }

    const sports = SPORT_CHOICES.map((choice) => choice.value).filter((sport) =>
      this.sports().includes(sport),
    );
    if (sports.length === 0) {
      this.sportsError.set(NO_SPORT);
      usable = false;
    } else {
      this.sportsError.set(null);
    }
    this.stretchingError.set(null);

    let own: OwnLimits | null = null;
    const levels = this.levelLimits();
    if (levels !== null) {
      const read = readOwnLimits(this.ownLimits(), levels[this.intensityLevel()]);
      if (read.ok) {
        own = read.value;
        this.intensityErrors.set({});
      } else {
        this.intensityErrors.set(read.errors);
        usable = false;
      }
    }

    if (this.limitations().length > LIMITATIONS_MAX) {
      this.limitationsError.set(`Use at most ${LIMITATIONS_MAX} characters.`);
      usable = false;
    } else {
      this.limitationsError.set(null);
    }

    return usable
      ? {
          weekdays,
          double_days: this.doubleDays(),
          time_windows: this.timeWindows(),
          weekly_budget_minutes: weeklyBudget,
          ...wishValues,
          ...preferenceValues,
          typical_weekly_minutes: typicalWeek,
          sports,
          stretching: this.stretching(),
          limitations: this.limitations(),
          share_limitations_text: this.shareText(),
          ...(own === null ? {} : { intensity_level: this.intensityLevel(), ...own }),
        }
      : null;
  }

  /** The fields as the server has them now, in the form people type them. */
  private show(availability: Availability): void {
    this.days.set(availability.weekdays.map(formatMinutes));
    this.budget.set(
      availability.weekly_budget_minutes === null
        ? ''
        : formatMinutes(availability.weekly_budget_minutes),
    );
    this.typical.set(
      availability.typical_weekly_minutes === null
        ? ''
        : formatMinutes(availability.typical_weekly_minutes),
    );
    this.sports.set([...availability.sports]);
    this.stretching.set(availability.stretching);
    this.limitations.set(availability.limitations);
    this.shareText.set(availability.share_limitations_text);
    this.preferences.set(
      preferenceForm(availability.sport_preferences, availability.strength_focus),
    );
    this.preferenceErrors.set({});
    this.preferencesError.set(null);
    this.wishes.set({
      trainingDays: numberText(availability.training_days),
      minimum:
        availability.min_weekly_minutes === null
          ? ''
          : formatMinutes(availability.min_weekly_minutes),
      longRunDay: numberText(availability.long_run_day),
      longRideDay: numberText(availability.long_ride_day),
    });
    this.wishErrors.set({});
    this.intensityLevel.set(availability.intensity_level);
    this.ownLimits.set(ownLimitTexts(availability));
    this.levelLimits.set(availability.level_limits);
    this.intensityErrors.set({});
    this.doubleDays.set([...availability.double_days]);
    this.timeWindows.set(availability.time_windows.map((day) => [...day]));
    this.windowErrors.set(NO_ERRORS);
    this.dayOptionsError.set(null);
    this.dayErrors.set(NO_ERRORS);
    this.weekdaysError.set(null);
    this.budgetError.set(null);
    this.typicalError.set(null);
    this.sportsError.set(null);
    this.stretchingError.set(null);
    this.limitationsError.set(null);
    this.shareTextError.set(null);
  }

  private showServerMessages(fields: Record<string, string[]>, all: string[]): void {
    const join = (name: string): string | null => fields[name]?.join(' ') ?? null;
    this.weekdaysError.set(join('weekdays'));
    this.dayOptionsError.set(
      [join('double_days'), join('time_windows')].filter((text) => text !== null).join(' ') || null,
    );
    this.budgetError.set(join('weekly_budget_minutes'));
    this.typicalError.set(join('typical_weekly_minutes'));
    this.sportsError.set(join('sports'));
    this.stretchingError.set(join('stretching'));
    this.limitationsError.set(join('limitations'));
    this.shareTextError.set(join('share_limitations_text'));
    this.preferencesError.set(
      [join('sport_preferences'), join('strength_focus')].filter((t) => t !== null).join(' ') ||
        null,
    );
    const wishes: WishErrors = {};
    for (const name of WISH_FIELDS) {
      const message = join(name);
      if (message !== null) {
        wishes[name] = message;
      }
    }
    this.wishErrors.set(wishes);
    const intensity: IntensityErrors = {};
    for (const name of ['intensity_level', ...LIMIT_NAMES] as const) {
      const message = join(name);
      if (message !== null) {
        intensity[name] = message;
      }
    }
    this.intensityErrors.set(intensity);
    const known = [
      'weekdays',
      'double_days',
      'time_windows',
      'weekly_budget_minutes',
      'typical_weekly_minutes',
      'sports',
      'stretching',
      'limitations',
      'share_limitations_text',
      'sport_preferences',
      'strength_focus',
      ...WISH_FIELDS,
      ...INTENSITY_FIELDS,
    ];
    const rest = Object.entries(fields)
      .filter(([name]) => !known.includes(name))
      .flatMap(([, texts]) => texts);
    this.errors.set(rest.length || Object.keys(fields).length ? rest : all);
  }
}
