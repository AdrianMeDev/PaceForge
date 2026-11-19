import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  computed,
  inject,
  input,
} from '@angular/core';
import { Season, SeasonAbsence, SeasonPhase } from '../../core/season/season-models';
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
  /** How many days of this week an illness covers (0 if none). */
  illnessDays: number;
  /** The races of the week as their letter (A, B, C) and the athlete's own title. */
  races: { letter: string; title: string }[];
  /** What a screen reader and the tooltip say about the week. */
  label: string;
}

/**
 * One cell for every week of the skeleton, in order. `today` is `YYYY-MM-DD`; the week that
 * contains it is the current one (none if today lies outside the season). Only illness periods
 * mark a week; other absences (vacation, other) leave the cell unmarked.
 */
export function timelineCells(
  season: Season,
  today: string,
  absences: readonly SeasonAbsence[] = [],
): TimelineCell[] {
  const illnesses = absences.filter((absence) => absence.kind === 'illness');
  return season.weeks.map((week) => {
    const races = week.races.map((race) => ({
      letter: PRIORITY_LETTERS[race.priority],
      title: race.title,
    }));
    const current = week.week_start <= today && today <= sundayOf(week.week_start);
    const illnessDays = illnessDaysInWeek(week.week_start, illnesses);
    const parts = [weekRange(week.week_start), PHASE_LABELS[week.phase]];
    if (week.recovery) {
      parts.push('Recovery week');
    }
    if (illnessDays > 0) {
      parts.push(`Illness, ${illnessDays === 1 ? '1 day' : `${illnessDays} days`}`);
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
      illnessDays,
      races,
      label: parts.join(' · '),
    };
  });
}

/** How many distinct days of the week starting on `monday` fall inside at least one illness. */
function illnessDaysInWeek(monday: string, illnesses: readonly SeasonAbsence[]): number {
  if (illnesses.length === 0) {
    return 0;
  }
  const [year, month, day] = monday.split('-').map(Number);
  const sunday = new Date(Date.UTC(year, month - 1, day + 6)).toISOString().slice(0, 10);
  const overlapping = illnesses.filter(
    (period) => period.start_date <= sunday && period.end_date >= monday,
  );
  if (overlapping.length === 0) {
    return 0;
  }
  let count = 0;
  for (let offset = 0; offset < 7; offset++) {
    const date = new Date(Date.UTC(year, month - 1, day + offset)).toISOString().slice(0, 10);
    if (overlapping.some((period) => period.start_date <= date && date <= period.end_date)) {
      count++;
    }
  }
  return count;
}

/** The Sunday of the week that starts on the given Monday, `YYYY-MM-DD`. */
function sundayOf(monday: string): string {
  const [year, month, day] = monday.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + 6)).toISOString().slice(0, 10);
}

/** Where to scroll the row so that a cell is in the middle of it (never before the start). */
export function centeredScroll(rowWidth: number, cellLeft: number, cellWidth: number): number {
  return Math.max(0, cellLeft - (rowWidth - cellWidth) / 2);
}

/**
 * The weeks of a season in a row: the phase of each week by colour and two letters, recovery weeks
 * and illness weeks marked, the races as their letter, the current week outlined. Every cell has
 * the whole story as text (tooltip and label); the titles of races are the athlete's own text and
 * only ever shown as text. The table below has the numbers.
 */
@Component({
  selector: 'app-season-timeline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ol class="timeline" aria-label="The weeks of the season by phase">
      @for (cell of cells(); track cell.week_start) {
        <li
          [attr.data-phase]="cell.phase"
          [attr.data-current]="cell.current ? 'true' : null"
          [attr.data-recovery]="cell.recovery ? 'true' : null"
          [attr.data-illness]="cell.illnessDays > 0 ? 'true' : null"
          [attr.aria-label]="cell.label"
          [attr.title]="cell.label"
          data-testid="timeline-cell"
        >
          <span class="phase" aria-hidden="true">{{ cell.abbreviation }}</span>
          <span class="mark" aria-hidden="true">{{ cell.recovery ? 'R' : '' }}</span>
          @if (cell.illnessDays > 0) {
            <span class="illness" data-testid="timeline-illness" aria-hidden="true">Ill</span>
          }
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
  /** Absences overlapping the live season; only illnesses are marked on the timeline. */
  readonly absences = input<readonly SeasonAbsence[]>([]);

  protected readonly cells = computed(() =>
    timelineCells(this.season(), this.today(), this.absences()),
  );

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  constructor() {
    // A season has up to 52 weeks: the row starts with this week in the middle. The row is moved
    // itself (not `scrollIntoView`), so the page does not jump when the row is below the fold.
    afterNextRender(() => {
      const row = this.host.nativeElement;
      const current = row.querySelector<HTMLElement>('[data-current="true"]');
      if (current) {
        row.scrollLeft = centeredScroll(row.clientWidth, current.offsetLeft, current.offsetWidth);
      }
    });
  }
}
