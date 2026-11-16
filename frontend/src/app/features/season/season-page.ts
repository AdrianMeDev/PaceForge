import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SeasonApi } from '../../core/season/season-api';
import { Season, SeasonPhase } from '../../core/season/season-models';
import { dayLabel, minutesText, weekRange } from '../planning/plan-format';
import { PHASE_HINTS, PHASE_LABELS, PRIORITY_LETTERS, raceText, usedShare } from './season-format';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** The phases a hint is written for, in the order of a season. */
const HINTED: SeasonPhase[] = ['base', 'build', 'specific', 'taper', 'transition'];

/**
 * The skeleton of the season: one row for every week up to the last A or B race, with the phase,
 * the minutes the skeleton plans and the races. The server works it out on every request from the
 * goals, the history and the availability of the user, so nothing is stored and a change of any
 * of them shows when the page is opened again.
 */
@Component({
  selector: 'app-season-page',
  imports: [RouterLink],
  templateUrl: './season-page.html',
  styleUrl: './season-page.css',
})
export class SeasonPage implements OnInit {
  private readonly api = inject(SeasonApi);

  protected readonly view = signal<View>('loading');
  protected readonly season = signal<Season | null>(null);

  /** The phases that occur, with what they are for. */
  protected readonly hints = computed(() => {
    const present = new Set(this.season()?.weeks.map((week) => week.phase) ?? []);
    return HINTED.filter((phase) => present.has(phase)).map((phase) => ({
      phase,
      label: PHASE_LABELS[phase],
      hint: PHASE_HINTS[phase],
    }));
  });

  protected readonly phaseLabel = PHASE_LABELS;
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
    }
  }
}
