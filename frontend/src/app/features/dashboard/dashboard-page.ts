import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DashboardApi } from '../../core/dashboard/dashboard-api';
import { Dashboard, WeekMinutes } from '../../core/dashboard/dashboard-models';
import { Rating } from '../../core/goals/goals-models';
import { SeasonPhase } from '../../core/season/season-models';
import { Icon } from '../../shared/icon';
import { PageHeader } from '../../shared/page-header';
import { KIND_LABELS, RATING_LABELS } from '../goals/goal-format';
import {
  SPORT_LABELS,
  dayLabel,
  minutesText,
  targetText,
  SPORT_ICONS,
  weekRange,
} from '../planning/plan-format';
import { PHASE_LABELS } from '../season/season-format';
import { MinutesChart } from './minutes-chart';
import { SetupChecklist, readHidden, setupComplete, writeHidden } from './setup-checklist';
import { StatTile } from './stat-tile';
import { WellnessTile } from './wellness-tile';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** The colour of the dot of a phase, as everywhere in the season. */
const PHASE_DOTS: Record<SeasonPhase, string> = {
  base: 'bg-phase-base',
  build: 'bg-phase-build',
  specific: 'bg-phase-specific',
  taper: 'bg-phase-taper',
  transition: 'bg-phase-transition',
};

/** The colours of the badge of a rating: as on the page of the goals, "realistic" has none. */
const RATING_BADGES: Record<Rating, string> = {
  realistic: '',
  ambitious: 'border-info text-info',
  unrealistic: 'border-danger text-danger',
  unknown: 'text-muted',
};

/**
 * The start page: what is next and how the week is going. The server works all of it out in one
 * request; the page only shows it. Every block says what to do next while it has nothing to show.
 * The titles are the user's own text and are only ever shown as text.
 */
@Component({
  selector: 'app-dashboard-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, MinutesChart, PageHeader, RouterLink, StatTile, SetupChecklist, WellnessTile],
  templateUrl: './dashboard-page.html',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(DashboardApi);

  protected readonly view = signal<View>('loading');
  protected readonly dashboard = signal<Dashboard | null>(null);

  protected readonly sportLabels = { ...SPORT_LABELS, other: 'Other' };
  protected readonly sportIcons = SPORT_ICONS;
  /** The user hid the card (kept in this browser). */
  protected readonly setupHidden = signal(readHidden());
  protected readonly setupComplete = setupComplete;

  protected hideSetup(): void {
    this.setupHidden.set(true);
    writeHidden(true);
  }

  protected showSetup(): void {
    this.setupHidden.set(false);
    writeHidden(false);
  }

  protected readonly day = dayLabel;
  protected readonly minutes = minutesText;
  protected readonly range = weekRange;
  protected readonly target = targetText;
  protected readonly phaseLabels = PHASE_LABELS;
  protected readonly phaseDots = PHASE_DOTS;
  protected readonly kindLabels = KIND_LABELS;
  protected readonly ratingLabels = RATING_LABELS;
  protected readonly ratingBadges = RATING_BADGES;

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
      this.dashboard.set(result.dashboard);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  /** How far along the minutes are, in percent; `null` while nothing is planned. */
  protected share(done: number, planned: number): number | null {
    return planned > 0 ? (100 * done) / planned : null;
  }

  protected rpe(value: number | null): string {
    return value === null ? '–' : value.toFixed(1);
  }

  /** "7 weeks to go"; the last week says so. */
  protected weeksLeft(weeks: number): string {
    if (weeks === 0) {
      return 'Less than a week to go';
    }
    return weeks === 1 ? '1 week to go' : `${weeks} weeks to go`;
  }

  /** The tokens of a call count, with thousands separated: "12,345". */
  protected tokens(count: number): string {
    return count.toLocaleString('en');
  }

  /** Whether any of the weeks has minutes: else there is nothing to draw. */
  protected anyMinutes(weeks: readonly WeekMinutes[]): boolean {
    return weeks.some((week) => week.sports.length > 0);
  }
}
