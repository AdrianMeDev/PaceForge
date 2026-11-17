import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Sport } from '../../core/activities/activities-models';
import { WeekMinutes } from '../../core/dashboard/dashboard-models';
import { minutesText, weekRange } from '../planning/plan-format';
import { SERIES_LABELS, SERIES_ORDER, niceAxis } from '../season/season-chart';

export interface MinutesSegment {
  sport: Sport;
  minutes: number;
  y: number;
  height: number;
  label: string;
}

export interface MinutesBar {
  week_start: string;
  x: number;
  total: number;
  segments: MinutesSegment[];
  /** The whole bar as text, for the tooltip and a screen reader. */
  label: string;
}

export interface MinutesLayout {
  width: number;
  height: number;
  left: number;
  ticks: { y: number; label: string }[];
  bars: MinutesBar[];
  /** The sports that occur, in the order of the legend. */
  sports: Sport[];
  labels: { x: number; text: string }[];
}

export const WIDTH = 320;
export const LEFT = 34;
export const RIGHT = 4;
export const TOP = 8;
export const PLOT_HEIGHT = 130;
export const BOTTOM = 20;
export const BAR_WIDTH = 22;

const SPORTS = SERIES_ORDER.filter((series): series is Sport => series !== 'aim');

/**
 * The geometry of the chart: one stacked bar per week with heights in proportion to the minutes on
 * a common axis, in the units of a picture of `WIDTH`. It is scaled to the width of its place. Pure:
 * the same weeks give the same picture.
 */
export function minutesLayout(weeks: readonly WeekMinutes[]): MinutesLayout {
  const sum = (week: WeekMinutes): number => week.sports.reduce((n, entry) => n + entry.minutes, 0);
  const { step, maxMinutes } = niceAxis(Math.max(0, ...weeks.map(sum)));
  const scale = PLOT_HEIGHT / maxMinutes;
  const bottom = TOP + PLOT_HEIGHT;
  const slot = (WIDTH - LEFT - RIGHT) / Math.max(weeks.length, 1);
  const present = new Set<Sport>();

  const bars = weeks.map((week, index): MinutesBar => {
    const x = LEFT + index * slot + (slot - BAR_WIDTH) / 2;
    const known = new Map(week.sports.map((entry) => [entry.sport, entry.minutes]));
    let used = 0;
    const segments: MinutesSegment[] = [];
    for (const sport of SPORTS) {
      const minutes = known.get(sport) ?? 0;
      if (minutes <= 0) {
        continue;
      }
      present.add(sport);
      used += minutes;
      segments.push({
        sport,
        minutes,
        y: bottom - used * scale,
        height: minutes * scale,
        label: `${SERIES_LABELS[sport]} ${minutesText(minutes)}`,
      });
    }
    const parts = [weekRange(week.week_start), ...segments.map((part) => part.label)];
    parts.push(used > 0 ? `${minutesText(used)} in all` : 'nothing done');
    return { week_start: week.week_start, x, total: used, segments, label: parts.join(' · ') };
  });

  const ticks: MinutesLayout['ticks'] = [];
  for (let hours = 0; hours * 60 <= maxMinutes; hours += step) {
    ticks.push({ y: bottom - hours * 60 * scale, label: `${hours} h` });
  }
  return {
    width: WIDTH,
    height: TOP + PLOT_HEIGHT + BOTTOM,
    left: LEFT,
    ticks,
    bars,
    sports: SPORTS.filter((sport) => present.has(sport)),
    labels: weeks.map((week, index) => ({
      x: LEFT + index * slot + slot / 2,
      text: weekRange(week.week_start).split(' – ')[0],
    })),
  };
}

// Written out in full, so that Tailwind finds the class names.
const FILLS: Record<Sport, string> = {
  running: 'fill-sport-running',
  cycling: 'fill-sport-cycling',
  swimming: 'fill-sport-swimming',
  strength: 'fill-sport-strength',
  other: 'fill-sport-other',
};
const SWATCHES: Record<Sport, string> = {
  running: 'bg-sport-running',
  cycling: 'bg-sport-cycling',
  swimming: 'bg-sport-swimming',
  strength: 'bg-sport-strength',
  other: 'bg-sport-other',
};

/**
 * The minutes done in the last weeks as stacked bars, one colour per sport, hours on the axis.
 * Every bar and part has its numbers as text in a `<title>`, and the legend names the colours: the
 * picture is never the only way to read them. Drawn from numbers only, no markup from outside.
 */
@Component({
  selector: 'app-minutes-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let chart = layout();
    <ul
      class="m-0 mb-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-sm"
      aria-label="What the colours mean"
    >
      @for (sport of chart.sports; track sport) {
        <li class="flex items-center gap-1.5">
          <span class="size-3 rounded-sm" [class]="swatches[sport]" aria-hidden="true"></span>
          {{ labels[sport] }}
        </li>
      }
    </ul>
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="block h-auto w-full"
      role="img"
      [attr.viewBox]="'0 0 ' + chart.width + ' ' + chart.height"
      aria-label="The minutes done in each of the last weeks, by sport"
      data-testid="chart"
    >
      @for (tick of chart.ticks; track tick.label) {
        <line
          class="stroke-border"
          stroke-width="1"
          [attr.x1]="chart.left"
          [attr.x2]="chart.width"
          [attr.y1]="tick.y"
          [attr.y2]="tick.y"
        />
        <text
          class="fill-muted"
          font-size="9"
          [attr.x]="chart.left - 4"
          [attr.y]="tick.y + 3"
          text-anchor="end"
        >
          {{ tick.label }}
        </text>
      }
      @for (bar of chart.bars; track bar.week_start) {
        <g [attr.data-testid]="'bar-' + bar.week_start">
          <title>{{ bar.label }}</title>
          @for (part of bar.segments; track part.sport) {
            <rect
              class="stroke-surface"
              stroke-width="1"
              [class]="fills[part.sport]"
              [attr.data-sport]="part.sport"
              [attr.x]="bar.x"
              [attr.y]="part.y"
              [attr.width]="barWidth"
              [attr.height]="part.height"
            >
              <title>{{ part.label }}</title>
            </rect>
          }
        </g>
      }
      @for (item of chart.labels; track item.x) {
        <text
          class="fill-muted"
          font-size="8"
          [attr.x]="item.x"
          [attr.y]="chart.height - 6"
          text-anchor="middle"
        >
          {{ item.text }}
        </text>
      }
    </svg>
  `,
})
export class MinutesChart {
  /** The weeks, the oldest first. */
  readonly weeks = input.required<readonly WeekMinutes[]>();

  protected readonly labels = SERIES_LABELS;
  protected readonly fills = FILLS;
  protected readonly swatches = SWATCHES;
  protected readonly barWidth = BAR_WIDTH;
  protected readonly layout = computed(() => minutesLayout(this.weeks()));
}
