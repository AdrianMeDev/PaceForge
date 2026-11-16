import { Component, computed, input } from '@angular/core';
import { Season, SeasonPlan } from '../../core/season/season-models';
import { SPORT_LABELS, minutesText, weekRange } from '../planning/plan-format';

/** What a bar is made of, bottom to top. `aim` is the skeleton's aim where there is no plan. */
export type Series = 'running' | 'cycling' | 'swimming' | 'strength' | 'other' | 'aim';

export const SERIES_ORDER: readonly Series[] = [
  'running',
  'cycling',
  'swimming',
  'strength',
  'other',
  'aim',
];

export const SERIES_LABELS: Record<Series, string> = {
  ...SPORT_LABELS,
  other: 'Other',
  aim: 'Aim of the skeleton',
};

/** One week as the chart gets it: minutes by series, in any order. */
export interface ChartWeek {
  week_start: string;
  planned: Partial<Record<Series, number>>;
}

export interface ChartSegment {
  series: Series;
  minutes: number;
  y: number;
  height: number;
  label: string;
}

export interface ChartBar {
  week_start: string;
  x: number;
  width: number;
  total: number;
  segments: ChartSegment[];
  /** The whole bar as text, for the tooltip of the week and a screen reader. */
  label: string;
}

export interface ChartTick {
  y: number;
  label: string;
}

export interface ChartLayout {
  width: number;
  height: number;
  left: number;
  top: number;
  plotHeight: number;
  /** The minutes at the top of the axis. */
  maxMinutes: number;
  ticks: ChartTick[];
  bars: ChartBar[];
  /** The series that occur, in the order of the legend. */
  series: Series[];
  /** The label under every `LABEL_EVERY`th bar. */
  labels: { x: number; text: string }[];
}

export const BAR_WIDTH = 14;
export const BAR_GAP = 6;
export const LEFT = 36;
export const RIGHT = 8;
export const TOP = 8;
export const PLOT_HEIGHT = 160;
export const BOTTOM = 22;
export const LABEL_EVERY = 4;
/** The steps of the hour axis, in hours; the smallest one with at most `MAX_TICKS` ticks wins. */
const STEPS = [1, 2, 5, 10, 20, 50];
const MAX_TICKS = 6;

/**
 * The axis: the step in hours and the top of the axis in minutes, a round number of steps that
 * holds the highest bar. Without any minutes the axis is one hour high, so that it has a scale.
 */
export function niceAxis(highest: number): { step: number; maxMinutes: number } {
  const hours = Math.max(highest, 1) / 60;
  const step = STEPS.find((candidate) => Math.ceil(hours / candidate) <= MAX_TICKS) ?? 100;
  return { step, maxMinutes: Math.ceil(hours / step) * step * 60 };
}

/**
 * The geometry of the chart: one stacked bar per week, heights in proportion to the minutes on a
 * common axis, in pixels of a picture that is as wide as it needs to be. Pure: the same weeks give
 * the same picture.
 */
export function chartLayout(weeks: readonly ChartWeek[]): ChartLayout {
  const totals = weeks.map((week) =>
    SERIES_ORDER.reduce((sum, s) => sum + (week.planned[s] ?? 0), 0),
  );
  const { step, maxMinutes } = niceAxis(Math.max(0, ...totals));
  const scale = PLOT_HEIGHT / maxMinutes;
  const bottom = TOP + PLOT_HEIGHT;
  const present = new Set<Series>();

  const bars = weeks.map((week, index): ChartBar => {
    let used = 0;
    const segments: ChartSegment[] = [];
    for (const series of SERIES_ORDER) {
      const minutes = week.planned[series] ?? 0;
      if (minutes <= 0) {
        continue;
      }
      present.add(series);
      used += minutes;
      const height = minutes * scale;
      segments.push({
        series,
        minutes,
        y: bottom - used * scale,
        height,
        label: `${SERIES_LABELS[series]} ${minutesText(minutes)}`,
      });
    }
    const parts = [weekRange(week.week_start), ...segments.map((s) => s.label)];
    parts.push(totals[index] > 0 ? `${minutesText(totals[index])} in all` : 'nothing planned');
    return {
      week_start: week.week_start,
      x: LEFT + index * (BAR_WIDTH + BAR_GAP),
      width: BAR_WIDTH,
      total: totals[index],
      segments,
      label: parts.join(' · '),
    };
  });

  const ticks: ChartTick[] = [];
  for (let hours = 0; hours * 60 <= maxMinutes; hours += step) {
    ticks.push({ y: bottom - hours * 60 * scale, label: `${hours} h` });
  }
  return {
    width: LEFT + weeks.length * (BAR_WIDTH + BAR_GAP) + RIGHT,
    height: TOP + PLOT_HEIGHT + BOTTOM,
    left: LEFT,
    top: TOP,
    plotHeight: PLOT_HEIGHT,
    maxMinutes,
    ticks,
    bars,
    series: SERIES_ORDER.filter((series) => present.has(series)),
    labels: weeks.flatMap((week, index) =>
      index % LABEL_EVERY === 0
        ? [
            {
              x: LEFT + index * (BAR_WIDTH + BAR_GAP) + BAR_WIDTH / 2,
              text: weekRange(week.week_start).split(' – ')[0],
            },
          ]
        : [],
    ),
  };
}

/** The weeks of a season for the chart: the plan's minutes by sport, else the skeleton's aim. */
export function chartWeeks(season: Season, plan: SeasonPlan | null): ChartWeek[] {
  return season.weeks.map((week, index) => {
    const filled = plan?.weeks[index];
    return {
      week_start: week.week_start,
      planned: filled ? { ...filled.minutes } : { aim: week.target_minutes },
    };
  });
}

/**
 * The planned minutes of every week as stacked bars, one colour per sport, hours on the axis.
 * Every bar and part has its numbers as text in a `<title>`, the legend names the colours and the
 * table of the page has all the numbers: the picture is never the only way to read them. Drawn
 * from numbers only, no markup from outside.
 */
@Component({
  selector: 'app-season-chart',
  template: `
    @if (layout(); as chart) {
      <ul class="legend" aria-label="What the colours mean">
        @for (series of chart.series; track series) {
          <li>
            <span class="swatch" [attr.data-series]="series" aria-hidden="true"></span>
            {{ labels[series] }}
          </li>
        }
      </ul>
      <div class="scroll">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          role="img"
          [attr.width]="chart.width"
          [attr.height]="chart.height"
          [attr.viewBox]="'0 0 ' + chart.width + ' ' + chart.height"
          [attr.aria-label]="label()"
          data-testid="chart"
        >
          @for (tick of chart.ticks; track tick.label) {
            <line
              class="grid"
              [attr.x1]="chart.left"
              [attr.x2]="chart.width"
              [attr.y1]="tick.y"
              [attr.y2]="tick.y"
            />
            <text class="axis" [attr.x]="chart.left - 4" [attr.y]="tick.y + 3" text-anchor="end">
              {{ tick.label }}
            </text>
          }
          @for (bar of chart.bars; track bar.week_start) {
            <g class="bar" [attr.data-testid]="'bar-' + bar.week_start">
              <title>{{ bar.label }}</title>
              @for (part of bar.segments; track part.series) {
                <rect
                  [attr.data-series]="part.series"
                  [attr.x]="bar.x"
                  [attr.y]="part.y"
                  [attr.width]="bar.width"
                  [attr.height]="part.height"
                >
                  <title>{{ part.label }}</title>
                </rect>
              }
            </g>
          }
          @for (item of chart.labels; track item.x) {
            <text class="axis" [attr.x]="item.x" [attr.y]="chart.height - 6" text-anchor="middle">
              {{ item.text }}
            </text>
          }
        </svg>
      </div>
    }
  `,
  styleUrl: './season-chart.css',
})
export class SeasonChart {
  readonly season = input.required<Season>();
  /** The version that is shown; without one the chart shows the aim of the skeleton. */
  readonly plan = input<SeasonPlan | null>(null);

  protected readonly labels = SERIES_LABELS;
  protected readonly layout = computed(() =>
    this.season().weeks.length === 0 ? null : chartLayout(chartWeeks(this.season(), this.plan())),
  );
  protected readonly label = computed(() =>
    this.plan() === null
      ? 'The minutes the skeleton aims for in each week of the season'
      : 'The minutes planned in each week of the season, by sport',
  );
}
