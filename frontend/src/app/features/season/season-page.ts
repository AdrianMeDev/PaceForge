import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { SeasonApi } from '../../core/season/season-api';
import {
  PlanProblem,
  Season,
  SeasonPhase,
  SeasonPlan,
  SeasonPlanVersion,
} from '../../core/season/season-models';
import { STATUS_LABELS, dayLabel, minutesText, weekRange } from '../planning/plan-format';
import { SeasonChart } from './season-chart';
import { SeasonTimeline } from './season-timeline';
import {
  FOCUS_LABELS,
  PHASE_HINTS,
  PHASE_LABELS,
  PRIORITY_LETTERS,
  doneText,
  keySessionText,
  localToday,
  minutesBySport,
  seasonFindingPlace,
  raceText,
  usedShare,
} from './season-format';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** The phases a hint is written for, in the order of a season. */
const HINTED: SeasonPhase[] = ['base', 'build', 'specific', 'taper', 'transition'];

/** What went wrong with the plans (the skeleton itself loads on its own). */
type Problem = 'list' | 'version' | 'missing' | null;
/** What the page is waiting for; one thing at a time. */
type Work = 'generating' | 'deciding' | 'opening';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That plan does not exist any more.';
const NO_TIME = 'You have no training time in the weeks of your season.';
const NOT_USABLE = 'The coach did not give a plan that could be used. Please try again.';
const TOO_MANY = 'Too many requests. Please wait a minute and try again.';
const NOT_A_DRAFT = 'That plan is not a draft any more.';
const HAS_ERRORS = 'The plan has errors and cannot be confirmed.';
const REFRESH_FAILED = 'The list of plans could not be refreshed. Please try again.';

/**
 * The season: one row for every week up to the last A or B race, with the phase, the minutes the
 * skeleton plans and the races. The server works it out on every request from the goals, the
 * history and the availability of the user, so nothing of it is stored and a change of any of
 * them shows when the page is opened again. Beside it is what the user's coach filled into the
 * weeks, one version at a time (the confirmed one, else the newest draft, opens on its own); a
 * version is shown with the skeleton it was made for. The coach's texts are only ever shown as
 * text. The user can draft a new version, read what the checks say about a draft, and confirm or
 * discard it; a draft with errors cannot be confirmed (the server decides and says why). Drafting
 * takes minutes, so the page says so and allows one thing at a time.
 */
@Component({
  selector: 'app-season-page',
  imports: [DatePipe, RouterLink, SeasonChart, SeasonTimeline],
  templateUrl: './season-page.html',
  styleUrl: './season-page.css',
})
export class SeasonPage implements OnInit {
  private readonly api = inject(SeasonApi);
  private readonly coach = inject(CoachApi);

  protected readonly view = signal<View>('loading');
  protected readonly season = signal<Season | null>(null);
  protected readonly versions = signal<SeasonPlanVersion[]>([]);
  /** The version that is shown, with its weeks. */
  protected readonly plan = signal<SeasonPlan | null>(null);
  protected readonly problem = signal<Problem>(null);
  protected readonly work = signal<Work | null>(null);
  protected readonly busy = computed(() => this.work() !== null);
  /** Whether an AI provider is set up; without one there is nothing to ask. */
  protected readonly configured = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** What was wrong with the answer of the coach, when it could not be used. */
  protected readonly problems = signal<PlanProblem[]>([]);
  /** No week offers any training time: the page says where to enter it. */
  protected readonly noTime = signal(false);

  /** The skeleton in the table: the one of the shown version, else today's. */
  protected readonly shown = computed(() => this.plan()?.skeleton ?? this.season());

  /** The version has the minutes done for some of its weeks. */
  protected readonly hasDone = computed(
    () => this.plan()?.weeks.some((week) => week.done !== null) ?? false,
  );
  protected readonly findings = computed(() => this.plan()?.report?.findings ?? []);
  protected readonly canConfirm = computed(
    () => this.plan()?.status === 'draft' && this.plan()?.report?.valid === true,
  );
  /** The version that a confirmed draft would replace. */
  protected readonly confirmed = computed(
    () => this.versions().find((version) => version.status === 'confirmed') ?? null,
  );

  /** The version was made for other weeks than the ones the skeleton has today. */
  protected readonly differs = computed(() => {
    const plan = this.plan();
    const today = this.season();
    return (
      plan !== null &&
      today !== null &&
      (plan.skeleton.weeks.length !== today.weeks.length ||
        plan.skeleton.weeks[0]?.week_start !== today.weeks[0]?.week_start)
    );
  });

  /** The phases that occur, with what they are for. */
  protected readonly hints = computed(() => {
    const present = new Set(this.shown()?.weeks.map((week) => week.phase) ?? []);
    return HINTED.filter((phase) => present.has(phase)).map((phase) => ({
      phase,
      label: PHASE_LABELS[phase],
      hint: PHASE_HINTS[phase],
    }));
  });

  protected readonly phaseLabel = PHASE_LABELS;
  protected readonly focusLabel = FOCUS_LABELS;
  protected readonly status = STATUS_LABELS;
  protected readonly bySport = minutesBySport;
  protected readonly done = doneText;
  protected readonly session = keySessionText;
  protected readonly letter = PRIORITY_LETTERS;
  protected readonly race = raceText;
  protected readonly minutes = minutesText;
  protected readonly range = weekRange;
  protected readonly day = dayLabel;
  protected readonly share = usedShare;
  protected readonly today = localToday();
  protected readonly place = (path: string): string =>
    seasonFindingPlace(
      path,
      (this.plan()?.weeks ?? []).map((week) => week.week_start),
    );

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const [result, provider] = await Promise.all([this.api.get(), this.coach.get()]);
      if (result.kind === 'forbidden' || provider.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.season.set(result.season);
      this.configured.set(provider.state.configured);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
      return;
    }
    await this.loadPlans();
  }

  /** Shows one of the versions: the one with this id. */
  protected async open(id: string): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    await this.show(id);
  }

  /** Asks the user's own coach to fill the season; the draft is shown with its checks. */
  protected async generate(): Promise<void> {
    if (this.busy() || !this.configured()) {
      return;
    }
    this.clearMessages();
    this.work.set('generating');
    try {
      const result = await this.api.generate();
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.notice.set('A draft was made. Please read it before you confirm it.');
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

  protected async confirm(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || !this.canConfirm()) {
      return;
    }
    this.clearMessages();
    this.work.set('deciding');
    try {
      const result = await this.api.confirm(current.id);
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
    if (this.busy() || current === null || current.status !== 'draft') {
      return;
    }
    this.clearMessages();
    this.work.set('deciding');
    try {
      const result = await this.api.discard(current.id);
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

  /** The version with this id on the screen; `work` is the page's while it loads. */
  private async show(id: string, announce = true): Promise<void> {
    this.work.set('opening');
    try {
      const result = await this.api.plan(id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          break;
        case 'not_found':
          if (announce) {
            this.problem.set('missing');
          }
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      if (announce) {
        this.problem.set('version');
      }
    } finally {
      this.work.set(null);
    }
  }

  /** Fetches the list of versions again without leaving the page. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.api.plans();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.versions.set(result.plans);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
    this.problems.set([]);
    this.noTime.set(false);
    this.problem.set(null);
  }

  /** The versions, and the one to open first: the confirmed one, else the newest draft. */
  private async loadPlans(): Promise<void> {
    this.problem.set(null);
    try {
      const result = await this.api.plans();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.versions.set(result.plans);
      const first =
        result.plans.find((version) => version.status === 'confirmed') ??
        result.plans.find((version) => version.status === 'draft');
      if (first) {
        await this.show(first.id);
      }
    } catch {
      this.problem.set('list');
    }
  }
}
