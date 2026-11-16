import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { PlanningApi } from '../../core/planning/planning-api';
import {
  PlanProblem,
  PlannableWeek,
  PushOutcome,
  Sport,
  WeekPlan,
  Workout,
} from '../../core/planning/planning-models';
import {
  GOAL_LABELS,
  SLOT_LABELS,
  SPORT_LABELS,
  STATUS_LABELS,
  dayLabel,
  exportSummaryText,
  exportText,
  findingPlace,
  minutesText,
  pushText,
  segmentText,
  exerciseDetail,
  REGION_LABELS,
  EQUIPMENT_LABELS,
  stretchingText,
  targetText,
  weekRange,
} from './plan-format';
import {
  FOCUS_LABELS,
  PHASE_LABELS,
  PRIORITY_LETTERS,
  keySessionText,
  minutesBySport,
} from '../season/season-format';
import { PlanEditor } from './plan-editor';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';
/** What the page is waiting for; one thing at a time. */
type Work = 'generating' | 'deciding' | 'opening' | 'sending' | 'restoring';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That plan does not exist any more.';
const REFRESH_FAILED = 'The list of plans could not be refreshed. Please try again.';
const NOT_PLANNABLE = 'This week cannot be planned.';
const NO_TIME = 'You have no training time for this week.';
const NOT_USABLE = 'The coach did not give a plan that could be used. Please try again.';
const TOO_MANY = 'Too many plans were requested. Please wait a minute and try again.';
const NOT_A_DRAFT = 'That plan is not a draft any more.';
const HAS_ERRORS = 'The plan has errors and cannot be confirmed.';
const NOT_RESTORABLE = 'Only a version that was replaced or discarded can be restored.';
const RESTORE_NOT_PLANNABLE =
  'This week cannot be planned any more, so a version of it cannot be restored.';
const TOO_MANY_PUSHES = 'Too many sends in a short time. Please wait a minute and try again.';

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
  imports: [RouterLink, DatePipe, PlanEditor],
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
  /** The week offers no training time: the page says where to enter it. */
  protected readonly noTime = signal(false);
  /** Intervals.icu is not usable: the page says where to connect it again. */
  protected readonly needsConnection = signal(false);
  /** Whether confirming a draft also sends the week to Intervals.icu (never without asking). */
  protected readonly sendAfterConfirm = signal(false);

  protected readonly week = computed(
    () => this.weeks().find((week) => week.week_start === this.selected()) ?? null,
  );
  protected readonly versions = computed(() => this.week()?.plans ?? []);
  /** What the confirmed season plan says about the week, if it says anything. */
  protected readonly season = computed(() => this.week()?.season ?? null);
  protected readonly confirmed = computed(
    () => this.versions().find((version) => version.status === 'confirmed') ?? null,
  );
  protected readonly days = computed<PlanDay[]>(() => this.group(this.plan()));
  protected readonly findings = computed(() => this.plan()?.report?.findings ?? []);
  /** The plan is being changed by hand: nothing else may start until that is saved or dropped. */
  protected readonly changing = signal(false);
  protected readonly busy = computed(() => this.work() !== null || this.changing());
  /** A draft and a confirmed plan can be changed; a version that was replaced is restored first. */
  protected readonly canChange = computed(
    () => this.plan()?.status === 'draft' || this.plan()?.status === 'confirmed',
  );
  /** A version that was replaced or discarded can be brought back as a new draft. */
  protected readonly canRestore = computed(
    () => this.plan()?.status === 'superseded' || this.plan()?.status === 'discarded',
  );
  protected readonly canConfirm = computed(
    () => this.plan()?.status === 'draft' && this.plan()?.report?.valid === true,
  );

  protected readonly slot = SLOT_LABELS;
  protected readonly sport = SPORT_LABELS;
  protected readonly goal = GOAL_LABELS;
  protected readonly status = STATUS_LABELS;
  protected readonly phase = PHASE_LABELS;
  protected readonly focus = FOCUS_LABELS;
  protected readonly letter = PRIORITY_LETTERS;
  protected readonly keySession = keySessionText;
  protected readonly seasonMinutes = (entries: { sport: Sport; minutes: number }[]): string =>
    minutesBySport(Object.fromEntries(entries.map((entry) => [entry.sport, entry.minutes])));
  protected readonly range = weekRange;
  protected readonly day = dayLabel;
  protected readonly stretching = stretchingText;
  protected readonly minutes = minutesText;
  protected readonly target = targetText;
  protected readonly segment = segmentText;
  protected readonly exerciseNumbers = exerciseDetail;
  protected readonly region = REGION_LABELS;
  protected readonly equipment = EQUIPMENT_LABELS;
  protected readonly place = findingPlace;
  protected readonly sent = exportText;
  protected readonly sentSummary = exportSummaryText;

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
    if (this.busy() || !this.weeks().some((week) => week.week_start === value)) {
      return;
    }
    this.clearMessages();
    this.plan.set(null);
    this.selected.set(value);
    await this.openDefault();
  }

  protected async open(id: string): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    await this.show(id);
  }

  protected async generate(): Promise<void> {
    if (this.busy() || !this.configured()) {
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
        case 'no_time':
          this.errors.set([NO_TIME]);
          this.noTime.set(true);
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

  protected startChanging(): void {
    if (this.busy() || !this.canChange()) {
      return;
    }
    this.clearMessages();
    this.changing.set(true);
  }

  /** The changes are dropped: nothing was stored before they were saved. */
  protected stopChanging(): void {
    this.changing.set(false);
  }

  /** The changes were stored as a new version of the week; it is shown, with its checks. */
  protected async changesSaved(plan: WeekPlan): Promise<void> {
    this.changing.set(false);
    this.clearMessages();
    this.plan.set(plan);
    const errors = plan.report?.valid === false;
    this.notice.set(
      `Your changes were saved as version ${plan.version}.` +
        (errors
          ? ' It has errors and cannot be confirmed yet.'
          : ' Read it, then confirm it to make it the plan of the week.'),
    );
    await this.refresh();
  }

  /** Brings the version on the screen back as a new draft; nothing else changes. */
  protected async restore(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || !this.canRestore()) {
      return;
    }
    this.clearMessages();
    this.work.set('restoring');
    try {
      const result = await this.planning.restore(current.id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.notice.set(
            `Version ${current.version} was restored as a new draft (version ${result.plan.version}).` +
              (result.plan.report?.valid === false
                ? ' With what you can do today it has errors and cannot be confirmed yet.'
                : ' Read it, then confirm it to make it the plan of the week.'),
          );
          await this.refresh();
          break;
        case 'not_found':
          this.plan.set(null);
          this.errors.set([GONE]);
          await this.refresh();
          break;
        case 'not_plannable':
          this.errors.set([RESTORE_NOT_PLANNABLE]);
          break;
        case 'not_restorable':
          // It has been decided on meanwhile: show it as it is now.
          this.errors.set([NOT_RESTORABLE]);
          await this.show(current.id, false);
          await this.refresh();
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

  protected signOut(): void {
    this.changing.set(false);
    this.view.set('signed_out');
  }

  protected async confirm(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || !this.canConfirm()) {
      return;
    }
    this.clearMessages();
    this.work.set('deciding');
    try {
      const result = await this.planning.confirm(current.id, this.sendAfterConfirm());
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.notice.set('The plan is confirmed.');
          if (result.push !== null) {
            this.report(result.push);
          }
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

  /** Sends the confirmed plan to Intervals.icu (again): what is in the calendar is updated. */
  protected async send(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || current.status !== 'confirmed') {
      return;
    }
    this.clearMessages();
    this.work.set('sending');
    try {
      const result = await this.planning.push(current.id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.report(result.push);
          break;
        case 'problem':
          this.errors.set([result.message]);
          this.needsConnection.set(
            result.problem === 'not_connected' || result.problem === 'invalid_key',
          );
          break;
        case 'not_found':
          this.plan.set(null);
          this.errors.set([GONE]);
          await this.refresh();
          break;
        case 'rate_limited':
          this.errors.set([TOO_MANY_PUSHES]);
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

  /** Says what a push did: a success as a notice, a problem as an error (with the way out). */
  private report(outcome: PushOutcome): void {
    if (outcome.ok) {
      this.notice.update((text) =>
        text === null ? pushText(outcome) : `${text} ${pushText(outcome)}`,
      );
      return;
    }
    this.errors.set([outcome.message]);
    this.needsConnection.set(
      outcome.problem === 'not_connected' || outcome.problem === 'invalid_key',
    );
  }

  protected async discard(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || current.status !== 'draft') {
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
    this.noTime.set(false);
    this.needsConnection.set(false);
  }
}
