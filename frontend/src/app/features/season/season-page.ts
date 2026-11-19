import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Injector,
  OnInit,
  afterNextRender,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { SeasonApi } from '../../core/season/season-api';
import {
  LiveSeason,
  PlanProblem,
  SeasonPhase,
  SeasonPlan,
  SeasonPlanVersion,
} from '../../core/season/season-models';
import {
  SPORT_LABELS,
  STATUS_LABELS,
  dayLabel,
  findingsSummary,
  loadText,
  minutesText,
  weekRange,
} from '../planning/plan-format';
import { compareSeasons } from './season-compare';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { VersionChips } from '../../shared/version-chips';
import { PageHeader } from '../../shared/page-header';
import { SeasonChangeNotice } from '../../shared/season-change-notice';
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
type Work = 'generating' | 'deciding' | 'opening' | 'restoring' | 'changing';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That plan does not exist any more.';
const NO_TIME = 'You have no training time in the weeks of your season.';
const NOT_USABLE = 'The coach did not give a plan that could be used. Please try again.';
const TOO_MANY = 'Too many requests. Please wait a minute and try again.';
const NOT_A_DRAFT = 'That plan is not a draft any more.';
const NOT_RESTORABLE = 'Only a version that was replaced or discarded can be restored.';
const NOT_CHANGEABLE =
  'Only the confirmed version and a draft can be changed. Restore an older version first.';
const UNCHANGED =
  'The coach gave the season back as it was. Say more clearly what you want changed.';
/** The longest request the server keeps (characters, as the server counts them). */
const REQUEST_MAX = 500;
const HAS_ERRORS = 'The plan has errors and cannot be confirmed.';
const STALE_LINK =
  'That version is no longer confirmed. Choose the confirmed version to ask for a change.';
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
  imports: [
    RouterLink,
    ConfirmDialog,
    PageHeader,
    SeasonChart,
    SeasonTimeline,
    VersionChips,
    SeasonChangeNotice,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './season-page.html',
  styleUrl: './season-page.css',
})
export class SeasonPage implements OnInit {
  private readonly api = inject(SeasonApi);
  private readonly coach = inject(CoachApi);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly injector = inject(Injector);
  private readonly changeNotice = viewChild(SeasonChangeNotice);
  private readonly requestField = viewChild<ElementRef<HTMLTextAreaElement>>('requestField');
  private readonly changeLink = signal<string | null>(null);
  private readonly plansLoaded = signal(false);

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.changeLink.set(params.get('change'));
    });
    effect(() => {
      const id = this.changeLink();
      if (id && this.plansLoaded() && this.view() === 'ready' && !this.busy()) {
        untracked(() => {
          this.changeLink.set(null);
          void this.openChangeLink(id);
        });
      }
    });
  }

  protected readonly view = signal<View>('loading');
  protected readonly season = signal<LiveSeason | null>(null);
  protected readonly versions = signal<SeasonPlanVersion[]>([]);
  /** The version that is shown, with its weeks. */
  protected readonly plan = signal<SeasonPlan | null>(null);
  protected readonly problem = signal<Problem>(null);
  /** The version the shown one was made from on request, to say what is different. */
  protected readonly parent = signal<SeasonPlan | null>(null);
  protected readonly parentMissing = signal(false);
  /** What the athlete is writing for a change, and what the server said about it. */
  protected readonly requestText = signal('');
  protected readonly requestError = signal<string | null>(null);
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
  /** The line under the title: how long the skeleton is. */
  protected readonly subtitle = computed(() => {
    const weeks = this.shown()?.weeks.length ?? 0;
    return this.view() !== 'ready' || weeks === 0
      ? ''
      : `${weeks} ${weeks === 1 ? 'week' : 'weeks'}`;
  });
  private readonly discardDialog = viewChild(ConfirmDialog);
  protected readonly shown = computed(() => this.plan()?.skeleton ?? this.season());
  /** The absences from the live season; a stored plan's skeleton does not carry them. */
  protected readonly absences = computed(() => this.season()?.absences ?? []);

  /** The version has the minutes done for some of its weeks. */
  protected readonly hasDone = computed(
    () => this.plan()?.weeks.some((week) => week.done !== null) ?? false,
  );
  protected readonly findings = computed(() => this.plan()?.report?.findings ?? []);
  protected readonly findingsText = computed(() => findingsSummary(this.findings()));
  protected readonly hasFindingErrors = computed(() =>
    this.findings().some((finding) => finding.severity === 'error'),
  );
  /** A version that was replaced or discarded can be brought back as a new draft. */
  protected readonly canRestore = computed(
    () => this.plan()?.status === 'superseded' || this.plan()?.status === 'discarded',
  );
  /** The confirmed version and a draft can be changed on request. */
  protected readonly canChange = computed(
    () => this.plan()?.status === 'confirmed' || this.plan()?.status === 'draft',
  );
  protected readonly requestMax = REQUEST_MAX;
  protected readonly requestLength = computed(() => [...this.requestText()].length);
  protected readonly requestFilled = computed(() => this.requestText().trim() !== '');
  /** What differs between the shown version and the one it was made from. */
  protected readonly differences = computed(() => {
    const plan = this.plan();
    const parent = this.parent();
    return plan !== null && parent !== null && plan.parent === parent.id
      ? compareSeasons(parent, plan)
      : null;
  });
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
  protected readonly sportLabel = SPORT_LABELS;
  protected readonly bySport = minutesBySport;
  protected readonly done = doneText;
  protected readonly session = keySessionText;
  protected readonly letter = PRIORITY_LETTERS;
  protected readonly race = raceText;
  protected readonly minutes = minutesText;
  protected readonly loadPoints = loadText;
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
    this.plansLoaded.set(false);
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
    this.plansLoaded.set(true);
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
          await this.setPlan(result.plan);
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
          await this.setPlan(result.plan);
          this.notice.set('The plan is confirmed.');
          await this.refresh();
          await this.changeNotice()?.reload();
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

  /** Asks the coach to change the version on the screen as the athlete wishes. */
  protected async change(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || !this.canChange() || !this.configured()) {
      return;
    }
    if (!this.requestFilled()) {
      return;
    }
    this.clearMessages();
    this.work.set('changing');
    try {
      const result = await this.api.change(current.id, this.requestText());
      switch (result.kind) {
        case 'ok':
          await this.setPlan(result.plan);
          this.requestText.set('');
          this.notice.set(
            `A changed draft was made from version ${current.version} (version ${result.plan.version}). ` +
              (result.plan.report?.valid === false
                ? 'It has errors and cannot be confirmed yet.'
                : 'Read what changed, then confirm it to make it the plan.'),
          );
          await this.refresh();
          break;
        case 'invalid':
          // the text stays, so that it can be corrected
          this.requestError.set((result.fields['request'] ?? result.errors).join(' '));
          break;
        case 'not_found':
          this.plan.set(null);
          this.errors.set([GONE]);
          await this.refresh();
          break;
        case 'not_changeable':
          // it has been decided on meanwhile: show it as it is now
          this.errors.set([NOT_CHANGEABLE]);
          await this.show(current.id, false);
          await this.refresh();
          break;
        case 'no_time':
          this.errors.set([NO_TIME]);
          this.noTime.set(true);
          break;
        case 'not_configured':
          this.configured.set(false);
          break;
        case 'unchanged':
          this.errors.set([UNCHANGED]);
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

  /** Brings the version on the screen back as a new draft; nothing else changes. */
  protected async restore(): Promise<void> {
    const current = this.plan();
    if (this.busy() || current === null || !this.canRestore()) {
      return;
    }
    this.clearMessages();
    this.work.set('restoring');
    try {
      const result = await this.api.restore(current.id);
      switch (result.kind) {
        case 'ok':
          await this.setPlan(result.plan);
          this.notice.set(
            `Version ${current.version} was restored as a new draft (version ${result.plan.version}).` +
              (result.plan.report?.valid === false
                ? ' It has errors and cannot be confirmed yet.'
                : ' Read it, then confirm it to make it the plan.'),
          );
          await this.refresh();
          break;
        case 'not_found':
          this.plan.set(null);
          this.errors.set([GONE]);
          await this.refresh();
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

  /** Discarding cannot be taken back with one click: the dialog asks first. */
  protected askToDiscard(): void {
    this.discardDialog()?.open();
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
        await this.setPlan(result.plan);
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

  /** A hint always targets the named confirmed plan, even while another version is shown. */
  private async openChangeLink(id: string): Promise<void> {
    this.clearMessages();
    if (this.confirmed()?.id !== id) {
      this.errors.set([STALE_LINK]);
    } else if (await this.show(id, true, true)) {
      afterNextRender(
        () => {
          if (this.plan()?.id === id && !this.busy()) {
            this.requestField()?.nativeElement.focus();
          }
        },
        { injector: this.injector },
      );
    }
    // Consume the request so following the same notice again works after viewing another version.
    if (this.route.snapshot.queryParamMap.get('change') === id) {
      await this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { change: null },
        queryParamsHandling: 'merge',
        fragment: 'season-change',
        replaceUrl: true,
      });
    }
  }

  /** The version with this id on the screen; `work` is the page's while it loads. */
  private async show(id: string, announce = true, confirmedOnly = false): Promise<boolean> {
    this.work.set('opening');
    try {
      const result = await this.api.plan(id);
      switch (result.kind) {
        case 'ok':
          if (confirmedOnly && result.plan.status !== 'confirmed') {
            this.errors.set([STALE_LINK]);
            return false;
          }
          await this.setPlan(result.plan);
          return true;
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
    return false;
  }

  /**
   * Puts a version on the screen. One that was made on request also gets the version it was made
   * from, to say what is different; if that cannot be loaded the page says so and shows the rest.
   */
  private async setPlan(plan: SeasonPlan): Promise<void> {
    this.plan.set(plan);
    this.parent.set(null);
    this.parentMissing.set(false);
    if (plan.request === '' || plan.parent === null) {
      return;
    }
    try {
      const result = await this.api.plan(plan.parent);
      if (result.kind === 'ok') {
        if (this.plan()?.id === plan.id) {
          this.parent.set(result.plan);
        }
      } else if (result.kind === 'forbidden') {
        this.view.set('signed_out');
      } else {
        this.parentMissing.set(true);
      }
    } catch {
      this.parentMissing.set(true);
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
    this.requestError.set(null);
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
