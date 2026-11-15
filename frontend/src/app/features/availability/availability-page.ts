import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  Availability,
  AvailabilityChanges,
  AvailabilitySport,
} from '../../core/availability/availability-models';
import {
  DAY_MAX_MINUTES,
  WEEKDAY_NAMES,
  WEEK_MAX_MINUTES,
  formatMinutes,
  parseMinutes,
} from './availability-format';
import { Parsed } from '../goals/goal-format';
import { PeriodsPanel } from './periods-panel';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const FALLBACK = 'Something went wrong. Please try again.';
const LIMITATIONS_MAX = 1000;
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

/** A day field: empty means no time. */
function dayMinutes(text: string): Parsed<number> {
  return text.trim() === '' ? { ok: true, value: 0 } : parseMinutes(text, DAY_MAX_MINUTES);
}

/**
 * How much time the user can train: minutes per weekday, an optional weekly budget that caps what
 * the days add up to, optionally what a normal week of training is for them (a reference for the
 * planning after a break, no limit), the sports they want in a plan, whether stretching may be
 * added to sessions, and limitations as free text. Everything is saved together with one Save.
 * What is checked here is what the server checks too, so that the message appears next to the
 * field; the server's own messages are shown the same way.
 */
@Component({
  selector: 'app-availability-page',
  imports: [RouterLink, PeriodsPanel],
  templateUrl: './availability-page.html',
  styleUrls: ['../auth/auth-form.css', './availability-page.css'],
})
export class AvailabilityPage implements OnInit {
  private readonly api = inject(AvailabilityApi);

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
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly dayErrors = signal<(string | null)[]>(NO_ERRORS);
  protected readonly weekdaysError = signal<string | null>(null);
  protected readonly budgetError = signal<string | null>(null);
  protected readonly typicalError = signal<string | null>(null);
  protected readonly sportsError = signal<string | null>(null);
  protected readonly stretchingError = signal<string | null>(null);
  protected readonly limitationsError = signal<string | null>(null);

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
    } catch {
      this.view.set('unreachable');
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

    if (this.limitations().length > LIMITATIONS_MAX) {
      this.limitationsError.set(`Use at most ${LIMITATIONS_MAX} characters.`);
      usable = false;
    } else {
      this.limitationsError.set(null);
    }

    return usable
      ? {
          weekdays,
          weekly_budget_minutes: weeklyBudget,
          typical_weekly_minutes: typicalWeek,
          sports,
          stretching: this.stretching(),
          limitations: this.limitations(),
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
    this.dayErrors.set(NO_ERRORS);
    this.weekdaysError.set(null);
    this.budgetError.set(null);
    this.typicalError.set(null);
    this.sportsError.set(null);
    this.stretchingError.set(null);
    this.limitationsError.set(null);
  }

  private showServerMessages(fields: Record<string, string[]>, all: string[]): void {
    const join = (name: string): string | null => fields[name]?.join(' ') ?? null;
    this.weekdaysError.set(join('weekdays'));
    this.budgetError.set(join('weekly_budget_minutes'));
    this.typicalError.set(join('typical_weekly_minutes'));
    this.sportsError.set(join('sports'));
    this.stretchingError.set(join('stretching'));
    this.limitationsError.set(join('limitations'));
    const known = [
      'weekdays',
      'weekly_budget_minutes',
      'typical_weekly_minutes',
      'sports',
      'stretching',
      'limitations',
    ];
    const rest = Object.entries(fields)
      .filter(([name]) => !known.includes(name))
      .flatMap(([, texts]) => texts);
    this.errors.set(rest.length || Object.keys(fields).length ? rest : all);
  }
}
