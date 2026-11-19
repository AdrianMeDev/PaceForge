import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { Season, SeasonPlan } from '../../core/season/season-models';
import { SPORT_LABELS, loadText, minutesText, weekRange } from '../planning/plan-format';

export type ChartMetric = 'minutes' | 'load';

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

/** One week as the chart gets it: minutes or load points by series, in any order. */
export interface ChartWeek {
  week_start: string;
  planned: Partial<Record<Series, number>>;
  /** Done values; `null`: not known (the week has not begun, or no confirmed plan). */
  done?: Partial<Record<Series, number>> | null;
}

export interface ChartSegment {
  series: Series;
  value: number;
  y: number;
  height: number;
  label: string;
}

/** A stack of parts: the planned bar, or the narrower done bar beside it. */
export interface ChartStack {
  x: number;
  width: number;
  total: number;
  segments: ChartSegment[];
}

export interface ChartBar extends ChartStack {
  week_start: string;
  /** Done values beside the plan; `null` where they are not known. */
  done: ChartStack | null;
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
  /** The minutes or load points at the top of the axis. */
  maxValue: number;
  ticks: ChartTick[];
  bars: ChartBar[];
  /** The series that occur, in the order of the legend. */
  series: Series[];
  /** Whether any week has done values beside its plan. */
  withDone: boolean;
  /** The label under every `LABEL_EVERY`th bar. */
  labels: { x: number; text: string }[];
}

export const BAR_WIDTH = 14;
/** The done bar is narrower, and stands right beside the planned one. */
export const DONE_WIDTH = 8;
export const DONE_GAP = 2;
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

/** A load-point axis with at most six round steps, including small or empty weeks. */
export function niceLoadAxis(highest: number): { step: number; maxLoad: number } {
  const value = Math.max(highest, 1);
  const magnitude = 10 ** Math.max(0, Math.floor(Math.log10(value / MAX_TICKS)));
  const step =
    [1, 2, 5, 10]
      .map((factor) => factor * magnitude)
      .find((size) => Math.ceil(value / size) <= MAX_TICKS) ?? magnitude * 10;
  return { step, maxLoad: Math.ceil(value / step) * step };
}

/**
 * The geometry of the chart: one stacked bar per week, heights in proportion to the values on a
 * common axis, in pixels of a picture that is as wide as it needs to be. Pure: the same weeks give
 * the same picture.
 */
export function chartLayout(
  weeks: readonly ChartWeek[],
  metric: ChartMetric = 'minutes',
): ChartLayout {
  const sum = (values: Partial<Record<Series, number>> | null | undefined): number =>
    SERIES_ORDER.reduce((total, series) => total + (values?.[series] ?? 0), 0);
  const withDone = weeks.some((week) => week.done != null);
  // A week with done values takes room for the second bar in every week, so they line up.
  const slot = BAR_WIDTH + (withDone ? DONE_GAP + DONE_WIDTH : 0) + BAR_GAP;
  const highest = Math.max(0, ...weeks.map((week) => Math.max(sum(week.planned), sum(week.done))));
  const axis = metric === 'load' ? niceLoadAxis(highest) : niceAxis(highest);
  const maxValue = 'maxLoad' in axis ? axis.maxLoad : axis.maxMinutes;
  const step = metric === 'load' ? axis.step : axis.step * 60;
  const text = metric === 'load' ? loadText : minutesText;
  const left = metric === 'load' ? Math.max(LEFT, loadText(maxValue).length * 6 + 8) : LEFT;
  const scale = PLOT_HEIGHT / maxValue;
  const bottom = TOP + PLOT_HEIGHT;
  const present = new Set<Series>();

  const stack = (
    values: Partial<Record<Series, number>>,
    x: number,
    width: number,
    prefix: string,
  ): ChartStack => {
    let used = 0;
    const segments: ChartSegment[] = [];
    for (const series of SERIES_ORDER) {
      const amount = values[series] ?? 0;
      if (amount <= 0) {
        continue;
      }
      present.add(series);
      used += amount;
      segments.push({
        series,
        value: amount,
        y: bottom - used * scale,
        height: amount * scale,
        label: `${prefix}${SERIES_LABELS[series]} ${text(amount)}`,
      });
    }
    return { x, width, total: used, segments };
  };

  const bars = weeks.map((week, index): ChartBar => {
    const x = left + index * slot;
    const planned = stack(week.planned, x, BAR_WIDTH, metric === 'load' ? 'Planned: ' : '');
    const done =
      week.done == null ? null : stack(week.done, x + BAR_WIDTH + DONE_GAP, DONE_WIDTH, 'Done: ');
    const parts = [weekRange(week.week_start), ...planned.segments.map((s) => s.label)];
    parts.push(planned.total > 0 ? `${text(planned.total)} planned` : 'nothing planned');
    if (done !== null) {
      if (metric === 'load') {
        parts.push(...done.segments.map((segment) => segment.label));
      }
      parts.push(done.total > 0 ? `${text(done.total)} done` : 'nothing done');
    }
    return { ...planned, week_start: week.week_start, done, label: parts.join(' · ') };
  });

  const ticks: ChartTick[] = [];
  for (let value = 0; value <= maxValue; value += step) {
    ticks.push({
      y: bottom - value * scale,
      label: metric === 'load' ? loadText(value) : `${value / 60} h`,
    });
  }
  return {
    width: left + weeks.length * slot + RIGHT,
    height: TOP + PLOT_HEIGHT + BOTTOM,
    left,
    top: TOP,
    plotHeight: PLOT_HEIGHT,
    maxValue,
    ticks,
    bars,
    withDone,
    series: SERIES_ORDER.filter((series) => present.has(series)),
    labels: weeks.flatMap((week, index) =>
      index % LABEL_EVERY === 0
        ? [
            {
              x: left + index * slot + BAR_WIDTH / 2,
              text: weekRange(week.week_start).split(' – ')[0],
            },
          ]
        : [],
    ),
  };
}

/** The plan's minutes or load by sport; only minutes have a skeleton aim to fall back to. */
export function chartWeeks(
  season: Season,
  plan: SeasonPlan | null,
  metric: ChartMetric = 'minutes',
): ChartWeek[] {
  return season.weeks.map((week, index) => {
    const filled = plan?.weeks[index];
    if (metric === 'load') {
      return {
        week_start: week.week_start,
        planned: { ...filled?.planned_load },
        done:
          filled?.done_load == null
            ? null
            : Object.fromEntries(filled.done_load.map((entry) => [entry.sport, entry.load])),
      };
    }
    return {
      week_start: week.week_start,
      planned: filled ? { ...filled.minutes } : { aim: week.target_minutes },
      done: filled?.done ? Object.fromEntries(filled.done.map((d) => [d.sport, d.minutes])) : null,
    };
  });
}

/**
 * Planned minutes or load points as stacked bars, one colour per sport, and for the weeks that
 * have begun the done values in a narrower bar beside them.
 * Every bar and part has its numbers as text in a `<title>`, the legend names the colours and the
 * table of the page has all the numbers: the picture is never the only way to read them. Drawn
 * from numbers only, no markup from outside.
 */
@Component({
  selector: 'app-season-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (layout(); as chart) {
      @if (plan()) {
        <div class="metric-toggle" role="group" aria-label="Season chart measure">
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            [attr.aria-pressed]="metric() === 'minutes'"
            (click)="selectedMetric.set('minutes')"
            data-testid="chart-minutes"
          >
            Minutes
          </button>
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            [attr.aria-pressed]="metric() === 'load'"
            (click)="selectedMetric.set('load')"
            data-testid="chart-load"
          >
            Load
          </button>
        </div>
        @if (metric() === 'load') {
          <p class="hint">Load points: planned estimates and known activity load.</p>
        }
      }
      <ul class="legend" aria-label="What the colours mean">
        @for (series of chart.series; track series) {
          <li>
            <span class="swatch" [attr.data-series]="series" aria-hidden="true"></span>
            {{ labels[series] }}
          </li>
        }
        @if (chart.withDone) {
          <li data-testid="legend-done">
            <span class="swatch done" aria-hidden="true"></span>
            Done: the narrow bar beside the plan, in the same colours
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
              @if (bar.done; as done) {
                @for (part of done.segments; track part.series) {
                  <rect
                    class="done"
                    [attr.data-series]="part.series"
                    [attr.x]="done.x"
                    [attr.y]="part.y"
                    [attr.width]="done.width"
                    [attr.height]="part.height"
                  >
                    <title>{{ part.label }}</title>
                  </rect>
                }
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
  protected readonly selectedMetric = signal<ChartMetric>('minutes');
  protected readonly metric = computed(() =>
    this.plan() === null ? 'minutes' : this.selectedMetric(),
  );

  protected readonly labels = SERIES_LABELS;
  protected readonly layout = computed(() =>
    this.season().weeks.length === 0
      ? null
      : chartLayout(chartWeeks(this.season(), this.plan(), this.metric()), this.metric()),
  );
  protected readonly label = computed(() =>
    this.metric() === 'load'
      ? 'The load points planned, and where known done, in each week of the season, by sport'
      : this.plan() === null
        ? 'The minutes the skeleton aims for in each week of the season'
        : 'The minutes planned, and where known done, in each week of the season, by sport',
  );
}
