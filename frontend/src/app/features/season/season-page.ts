import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SeasonApi } from '../../core/season/season-api';
import {
  Season,
  SeasonPhase,
  SeasonPlan,
  SeasonPlanVersion,
} from '../../core/season/season-models';
import { STATUS_LABELS, dayLabel, minutesText, weekRange } from '../planning/plan-format';
import {
  FOCUS_LABELS,
  PHASE_HINTS,
  PHASE_LABELS,
  PRIORITY_LETTERS,
  keySessionText,
  minutesBySport,
  raceText,
  usedShare,
} from './season-format';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** The phases a hint is written for, in the order of a season. */
const HINTED: SeasonPhase[] = ['base', 'build', 'specific', 'taper', 'transition'];

/** What went wrong with the plans (the skeleton itself loads on its own). */
type Problem = 'list' | 'version' | 'missing' | null;

/**
 * The season: one row for every week up to the last A or B race, with the phase, the minutes the
 * skeleton plans and the races. The server works it out on every request from the goals, the
 * history and the availability of the user, so nothing of it is stored and a change of any of
 * them shows when the page is opened again. Beside it is what the user's coach filled into the
 * weeks, one version at a time (the confirmed one, else the newest draft, opens on its own); a
 * version is shown with the skeleton it was made for. The coach's texts are only ever shown as
 * text.
 */
@Component({
  selector: 'app-season-page',
  imports: [DatePipe, RouterLink],
  templateUrl: './season-page.html',
  styleUrl: './season-page.css',
})
export class SeasonPage implements OnInit {
  private readonly api = inject(SeasonApi);

  protected readonly view = signal<View>('loading');
  protected readonly season = signal<Season | null>(null);
  protected readonly versions = signal<SeasonPlanVersion[]>([]);
  /** The version that is shown, with its weeks. */
  protected readonly plan = signal<SeasonPlan | null>(null);
  protected readonly problem = signal<Problem>(null);
  protected readonly busy = signal(false);

  /** The skeleton in the table: the one of the shown version, else today's. */
  protected readonly shown = computed(() => this.plan()?.skeleton ?? this.season());

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
  protected readonly session = keySessionText;
  protected readonly letter = PRIORITY_LETTERS;
  protected readonly race = raceText;
  protected readonly minutes = minutesText;
  protected readonly range = weekRange;
  protected readonly day = dayLabel;
  protected readonly share = usedShare;

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
      this.season.set(result.season);
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
    this.busy.set(true);
    try {
      const result = await this.api.plan(id);
      switch (result.kind) {
        case 'ok':
          this.plan.set(result.plan);
          this.problem.set(null);
          break;
        case 'not_found':
          this.problem.set('missing');
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.problem.set('version');
    } finally {
      this.busy.set(false);
    }
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
        await this.open(first.id);
      }
    } catch {
      this.problem.set('list');
    }
  }
}
