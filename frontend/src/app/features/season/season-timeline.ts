import { Component, computed, input } from '@angular/core';
import { Season, SeasonPhase } from '../../core/season/season-models';
import { weekRange } from '../planning/plan-format';
import { PHASE_LABELS, PRIORITY_LETTERS } from './season-format';

/** Two letters for a phase: the colour is not the only signal. */
export const PHASE_ABBREVIATIONS: Record<SeasonPhase, string> = {
  base: 'Ba',
  build: 'Bu',
  specific: 'Sp',
  taper: 'Ta',
  transition: 'Tr',
};

/** One week of the timeline. */
export interface TimelineCell {
  week_start: string;
  phase: SeasonPhase;
  abbreviation: string;
  recovery: boolean;
  /** The week that contains today. */
  current: boolean;
  /** The races of the week as their letter (A, B, C) and the athlete's own title. */
  races: { letter: string; title: string }[];
  /** What a screen reader and the tooltip say about the week. */
  label: string;
}

/**
 * One cell for every week of the skeleton, in order. `today` is `YYYY-MM-DD`; the week that
 * contains it is the current one (none if today lies outside the season).
 */
export function timelineCells(season: Season, today: string): TimelineCell[] {
  return season.weeks.map((week) => {
    const races = week.races.map((race) => ({
      letter: PRIORITY_LETTERS[race.priority],
      title: race.title,
    }));
    const current = week.week_start <= today && today <= sundayOf(week.week_start);
    const parts = [weekRange(week.week_start), PHASE_LABELS[week.phase]];
    if (week.recovery) {
      parts.push('Recovery week');
    }
    for (const race of races) {
      parts.push(`${race.letter} race ${race.title}`.trim());
    }
    if (current) {
      parts.push('This week');
    }
    return {
      week_start: week.week_start,
      phase: week.phase,
      abbreviation: PHASE_ABBREVIATIONS[week.phase],
      recovery: week.recovery,
      current,
      races,
      label: parts.join(' · '),
    };
  });
}

/** The Sunday of the week that starts on the given Monday, `YYYY-MM-DD`. */
function sundayOf(monday: string): string {
  const [year, month, day] = monday.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + 6)).toISOString().slice(0, 10);
}

/**
 * The weeks of a season in a row: the phase of each week by colour and two letters, recovery weeks
 * marked, the races as their letter, the current week outlined. Every cell has the whole story as
 * text (tooltip and label); the titles of races are the athlete's own text and only ever shown as
 * text. The table below has the numbers.
 */
@Component({
  selector: 'app-season-timeline',
  template: `
    <ol class="timeline" aria-label="The weeks of the season by phase">
      @for (cell of cells(); track cell.week_start) {
        <li
          [attr.data-phase]="cell.phase"
          [attr.data-current]="cell.current ? 'true' : null"
          [attr.data-recovery]="cell.recovery ? 'true' : null"
          [attr.aria-label]="cell.label"
          [attr.title]="cell.label"
          data-testid="timeline-cell"
        >
          <span class="phase" aria-hidden="true">{{ cell.abbreviation }}</span>
          <span class="mark" aria-hidden="true">{{ cell.recovery ? 'R' : '' }}</span>
          <span class="races" aria-hidden="true">
            @for (race of cell.races; track $index) {
              <span class="race" data-testid="timeline-race">{{ race.letter }}</span>
            }
          </span>
        </li>
      }
    </ol>
  `,
  styleUrl: './season-timeline.css',
})
export class SeasonTimeline {
  readonly season = input.required<Season>();
  /** The day it is for the user, `YYYY-MM-DD`. */
  readonly today = input.required<string>();

  protected readonly cells = computed(() => timelineCells(this.season(), this.today()));
}
