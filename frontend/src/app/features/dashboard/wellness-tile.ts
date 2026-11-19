import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import {
  WellnessMetric,
  WellnessSummary,
  WellnessTrend,
} from '../../core/dashboard/dashboard-models';
import { Icon } from '../../shared/icon';
import { minutesText } from '../planning/plan-format';

/** The arrows and words of a trend, in the order a metric improves or worsens. */
const TREND_ARROWS: Record<WellnessTrend, string> = {
  up: '↑',
  down: '↓',
  flat: '→',
};

const TREND_LABELS: Record<WellnessTrend, string> = {
  up: 'Up',
  down: 'Down',
  flat: 'Flat',
};

/** One metric of the tile: what to call it and how its number is shown. */
interface MetricSpec {
  key: 'sleep' | 'hrv' | 'resting_hr' | 'weight';
  label: string;
  /** Formats the measurement as a number without the unit. */
  format: (value: number) => string;
  /** The unit shown after the number, or a blank for none (sleep is a duration). */
  unit: string;
}

const METRICS: readonly MetricSpec[] = [
  { key: 'sleep', label: 'Sleep', format: minutesText, unit: '' },
  { key: 'hrv', label: 'HRV', format: (value) => value.toFixed(1), unit: 'ms' },
  { key: 'resting_hr', label: 'Resting HR', format: (value) => value.toFixed(0), unit: 'bpm' },
  { key: 'weight', label: 'Weight', format: (value) => value.toFixed(1), unit: 'kg' },
];

/** What a recovery warning names: the metric it is about. */
const SIGNAL_LABELS: Record<string, string> = {
  low_sleep: 'sleep is shorter than usual',
  low_hrv: 'HRV is lower than usual',
  high_resting_hr: 'resting heart rate is higher than usual',
};

/**
 * The synced wellness of the last 7 days against the 28 days before. Each metric shows its recent
 * mean and, where there is a baseline, an arrow for the trend and how it compares to the usual. A
 * warning banner appears whenever recovery is clearly worse than usual. With no summary, or with
 * no readings for a metric, the tile says so instead of guessing.
 */
@Component({
  selector: 'app-wellness-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <div class="flex h-full flex-col rounded-md border border-border bg-surface p-4 shadow-card">
      <h3 class="m-0 mb-2 flex items-center gap-2 text-lg font-semibold" data-testid="wellness">
        <app-icon name="activity" [label]="'Wellness'" />
        Wellness and readiness
      </h3>

      @if (wellness(); as summary) {
        @if (summary.warning) {
          <div
            class="notice notice-warning mb-3 flex items-start gap-2"
            role="alert"
            data-testid="wellness-warning"
          >
            <app-icon name="alert-triangle" [label]="'Recovery warning'" />
            <span data-testid="wellness-warning-text">{{ warningText(summary) }}</span>
          </div>
        }

        <dl class="m-0 grid grid-cols-1 gap-3 sm:grid-cols-2">
          @for (metric of specs(); track metric.key) {
            <div class="rounded-md bg-surface-2 p-3" [attr.data-testid]="'wellness-' + metric.key">
              <dt class="text-sm text-muted">{{ metric.label }}</dt>
              @if (reading(summary[metric.key], metric); as shown) {
                <dd class="m-0 mt-1 text-xl font-semibold">
                  {{ shown }}
                  @if (metric.unit) {
                    <span class="text-sm font-normal text-muted">{{ ' ' + metric.unit }}</span>
                  }
                </dd>
                @if (trendLine(summary[metric.key], metric); as line) {
                  <dd class="m-0 text-sm text-muted" [attr.data-testid]="'trend-' + metric.key">
                    {{ line }}
                  </dd>
                }
              } @else {
                <dd class="m-0 mt-1 text-muted" [attr.data-testid]="'missing-' + metric.key">
                  No recent {{ metric.label.toLowerCase() }}
                </dd>
              }
            </div>
          }
        </dl>
      } @else {
        <p class="m-0 text-muted" data-testid="wellness-empty">
          No wellness data synced yet. Connect Intervals.icu to see your sleep, HRV, resting heart
          rate and weight here.
        </p>
      }
    </div>
  `,
})
export class WellnessTile {
  readonly wellness = input.required<WellnessSummary | null>();

  protected readonly specs = () => METRICS;

  /** The reading shown to the athlete, or `null` when there is none. */
  protected reading(metric: WellnessMetric, spec: Readonly<MetricSpec>): string | null {
    return metric.recent === null ? null : spec.format(metric.recent);
  }

  /** "↓ Down, 500 usual" with a baseline, the bare arrow and word without one, else `null`. */
  protected trendLine(metric: WellnessMetric, spec: Readonly<MetricSpec>): string | null {
    if (metric.trend === null) {
      return null;
    }
    const arrow = TREND_ARROWS[metric.trend];
    const label = TREND_LABELS[metric.trend];
    if (metric.recent !== null && metric.baseline !== null) {
      return `${arrow} ${label}, ${spec.format(metric.baseline)} usual`;
    }
    return `${arrow} ${label}`;
  }

  /** One sentence naming each metric that is clearly worse than usual. */
  protected warningText(summary: WellnessSummary): string {
    const names = summary.warning_signals.map((signal) => SIGNAL_LABELS[signal] ?? signal);
    if (names.length === 0) {
      return 'Your recovery is worse than usual.';
    }
    if (names.length === 1) {
      return `Your ${names[0]}.`;
    }
    return `Your ${names.slice(0, -1).join(' and ')} and ${names[names.length - 1]}.`;
  }
}
