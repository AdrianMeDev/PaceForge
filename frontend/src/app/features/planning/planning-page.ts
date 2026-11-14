import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { PlanningApi } from '../../core/planning/planning-api';
import { PlanProblem, PlannableWeek, WeekPlan, Workout } from '../../core/planning/planning-models';
import {
  GOAL_LABELS,
  SPORT_LABELS,
  STATUS_LABELS,
  dayLabel,
  findingPlace,
  minutesText,
  segmentText,
  targetText,
  weekRange,
} from './plan-format';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';
/** What the page is waiting for; one thing at a time. */
type Work = 'generating' | 'deciding' | 'opening';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That plan does not exist any more.';
const REFRESH_FAILED = 'The list of plans could not be refreshed. Please try again.';
const NOT_PLANNABLE = 'This week cannot be planned.';
const NOT_USABLE = 'The coach did not give a plan that could be used. Please try again.';
const TOO_MANY = 'Too many plans were requested. Please wait a minute and try again.';
const NOT_A_DRAFT = 'That plan is not a draft any more.';
const HAS_ERRORS = 'The plan has errors and cannot be confirmed.';

/** One day of the plan with its workouts, numbered as the checks number them. */
interface PlanDay {
  date: string;
  label: string;
  workouts: { number: number; workout: Workout }[];
}

/**
 * The weekly plan: pick a week, let the user's own coach draft it, read the draft with what the
 * checks say about it, then confirm or discard it. Nothing the coach writes is trusted: the
 * client has checked every field, and a plan with errors cannot be confirmed (the server decides
 * and says why). Drafting takes a while, so the page says so and allows one thing at a time.
 */
@Component({
  selector: 'app-planning-page',
  imports: [RouterLink, DatePipe],
  templateUrl: './planning-page.html',
  styleUrls: ['../auth/auth-form.css', './planning-page.css'],
})
export class PlanningPage implements OnInit {
  private readonly planning = inject(PlanningApi);
  private readonly coach = inject(CoachApi);

  protected readonly view = signal<View>('loading');
  protected readonly weeks = signal<PlannableWeek[]>([]);
  /** Whether an AI provider is set up; without one there is nothing to ask. */
  protected readonly configured = signal(false);
  protected readonly selected = signal('');
  protected readonly plan = signal<WeekPlan | null>(null);
  protected readonly work = signal<Work | null>(null);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** What was wrong with the answer of the coach, when it could not be used. */
  protected readonly problems = signal<PlanProblem[]>([]);

  protected readonly week = computed(
    () => this.weeks().find((week) => week.week_start === this.selected()) ?? null,
  );
  protected readonly versions = computed(() => this.week()?.plans ?? []);
  protected readonly confirmed = computed(
    () => this.versions().find((version) => version.status === 'confirmed') ?? null,
  );
  protected readonly days = computed<PlanDay[]>(() => this.group(this.plan()));
  protected readonly findings = computed(() => this.plan()?.report?.findings ?? []);
  protected readonly canConfirm = computed(
    () => this.plan()?.status === 'draft' && this.plan()?.report?.valid === true,
  );

  protected readonly sport = SPORT_LABELS;
  protected readonly goal = GOAL_LABELS;
  protected readonly status = STATUS_LABELS;
  protected readonly range = weekRange;
  protected readonly minutes = minutesText;
  protected readonly target = targetText;
  protected readonly segment = segmentText;
  protected readonly place = findingPlace;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const [weeks, provider] = await Promise.all([this.planning.weeks(), this.coach.get()]);
      if (weeks.kind === 'forbidden' || provider.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.weeks.set(weeks.weeks);
      this.configured.set(provider.state.configured);
      // Next week is the usual one to plan; the first week is the one that is running now.
      this.selected.set((weeks.weeks[1] ?? weeks.weeks[0])?.week_start ?? '');
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
      return;
    }
    await this.openDefault();
  }

  protected async selectWeek(value: string): Promise<void> {
    if (this.work() !== null || !this.weeks().some((week) => week.week_start === value)) {
      return;
    }
    this.clearMessages();
    this.plan.set(null);
    this.selected.set(value);
    await this.openDefault();
  }

  protected async open(id: string): Promise<void> {
    if (this.work() !== null) {
      return;
    }
    this.clearMessages();
    await this.show(id);
  }

  protected async generate(): Promise<void> {
    if (this.work() !== null || !this.configured()) {
      return;
    }
    this.clearMessages();
    this.work.set('generating');
    try {
      const result = await this.planning.generate(this.selected());
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.notice.set('A draft was made. Please read it before you confirm it.');
          await this.refresh();
          break;
        case 'not_plannable':
          this.errors.set([NOT_PLANNABLE]);
          await this.refresh();
          break;
        case 'not_configured':
          this.configured.set(false);
          break;
        case 'not_usable':
          this.errors.set([NOT_USABLE]);
          this.problems.set(result.problems);
          break;
        case 'provider_problem':
          this.errors.set([
            result.retry_after === null
              ? result.message
              : `${result.message} Try again in ${result.retry_after} seconds.`,
          ]);
          break;
        case 'rate_limited':
          this.errors.set([TOO_MANY]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.work.set(null);
    }
  }

  protected async confirm(): Promise<void> {
    const current = this.plan();
    if (this.work() !== null || current === null || !this.canConfirm()) {
      return;
    }
    this.clearMessages();
    this.work.set('deciding');
    try {
      const result = await this.planning.confirm(current.id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.notice.set('The plan is confirmed.');
          await this.refresh();
          break;
        case 'not_confirmable':
          this.plan.set({ ...current, report: { valid: false, findings: result.findings } });
          this.errors.set([HAS_ERRORS]);
          break;
        default:
          await this.decided(result.kind, current.id);
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.work.set(null);
    }
  }

  protected async discard(): Promise<void> {
    const current = this.plan();
    if (this.work() !== null || current === null || current.status !== 'draft') {
      return;
    }
    this.clearMessages();
    this.work.set('deciding');
    try {
      const result = await this.planning.discard(current.id);
      if (result.kind === 'ok') {
        this.plan.set(result.plan);
        this.notice.set('The draft was discarded.');
        await this.refresh();
      } else {
        await this.decided(result.kind, current.id);
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.work.set(null);
    }
  }

  /** What the page does when confirming or discarding did not go through as a decision. */
  private async decided(
    kind: 'not_found' | 'not_a_draft' | 'forbidden',
    id: string,
  ): Promise<void> {
    if (kind === 'forbidden') {
      this.view.set('signed_out');
    } else if (kind === 'not_found') {
      this.plan.set(null);
      this.errors.set([GONE]);
      await this.refresh();
    } else {
      this.errors.set([NOT_A_DRAFT]);
      await this.show(id, false);
      await this.refresh();
    }
  }

  /** Shows the plan that is most likely wanted: the newest draft or confirmed version. */
  private async openDefault(): Promise<void> {
    const version = this.versions().find(
      (candidate) => candidate.status === 'draft' || candidate.status === 'confirmed',
    );
    if (version !== undefined) {
      await this.show(version.id);
    }
  }

  private async show(id: string, announce = true): Promise<void> {
    this.work.set('opening');
    try {
      const result = await this.planning.get(id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          break;
        case 'not_found':
          this.plan.set(null);
          if (announce) {
            this.errors.set([GONE]);
            await this.refresh();
          }
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.update((list) => [...list, FALLBACK]);
    } finally {
      this.work.set(null);
    }
  }

  /** Fetches the weeks again without leaving the page; a failure is shown above the plan. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.planning.weeks();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.weeks.set(result.weeks);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private group(plan: WeekPlan | null): PlanDay[] {
    const days: PlanDay[] = [];
    plan?.workouts.forEach((workout, index) => {
      let day = days.find((candidate) => candidate.date === workout.day);
      if (day === undefined) {
        day = { date: workout.day, label: dayLabel(workout.day), workouts: [] };
        days.push(day);
      }
      day.workouts.push({ number: index + 1, workout });
    });
    return days;
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
    this.problems.set([]);
  }
}
