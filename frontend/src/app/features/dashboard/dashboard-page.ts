import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DashboardApi } from '../../core/dashboard/dashboard-api';
import { Dashboard, NextWorkout } from '../../core/dashboard/dashboard-models';
import { IconName, Icon } from '../../shared/icon';
import { PageHeader } from '../../shared/page-header';
import {
  SPORT_LABELS,
  dayLabel,
  minutesText,
  targetText,
  weekRange,
} from '../planning/plan-format';
import { StatTile } from './stat-tile';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const SPORT_ICONS: Record<NextWorkout['sport'], IconName> = {
  running: 'running',
  cycling: 'bike',
  swimming: 'waves',
  strength: 'dumbbell',
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
}
