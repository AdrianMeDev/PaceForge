import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DashboardApi } from '../../core/dashboard/dashboard-api';
import { Dashboard, NextWorkout } from '../../core/dashboard/dashboard-models';
import { Rating } from '../../core/goals/goals-models';
import { SeasonPhase } from '../../core/season/season-models';
import { IconName, Icon } from '../../shared/icon';
import { PageHeader } from '../../shared/page-header';
import { KIND_LABELS, RATING_LABELS } from '../goals/goal-format';
import {
  SPORT_LABELS,
  dayLabel,
  minutesText,
  targetText,
  weekRange,
} from '../planning/plan-format';
import { PHASE_LABELS } from '../season/season-format';
import { StatTile } from './stat-tile';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const SPORT_ICONS: Record<NextWorkout['sport'], IconName> = {
  running: 'running',
  cycling: 'bike',
  swimming: 'waves',
  strength: 'dumbbell',
};

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
  imports: [Icon, PageHeader, RouterLink, StatTile],
  templateUrl: './dashboard-page.html',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(DashboardApi);

  protected readonly view = signal<View>('loading');
  protected readonly dashboard = signal<Dashboard | null>(null);

  protected readonly sportLabels = SPORT_LABELS;
  protected readonly sportIcons = SPORT_ICONS;
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
}
