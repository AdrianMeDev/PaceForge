import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WellnessSummary } from '../../core/dashboard/dashboard-models';
import { query } from '../../testing/dom';
import { WellnessTile } from './wellness-tile';

const FULL: WellnessSummary = {
  sleep: { recent: 450, baseline: 500, trend: 'down' },
  hrv: { recent: 55, baseline: 50, trend: 'up' },
  resting_hr: { recent: 54, baseline: 50, trend: 'up' },
  weight: { recent: 72.5, baseline: 72.5, trend: 'flat' },
  warning: true,
  warning_signals: ['low_sleep', 'high_resting_hr'],
};

describe('WellnessTile', () => {
  let fixture: ComponentFixture<WellnessTile>;

  function show(wellness: WellnessSummary | null): HTMLElement {
    fixture = TestBed.createComponent(WellnessTile);
    fixture.componentRef.setInput('wellness', wellness);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  function text(root: HTMLElement, selector: string): string {
    return (query(root, selector).textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  /** The value and trend of one metric, as the two lines under its label. */
  function lines(root: HTMLElement, key: string): { value: string; trend: string | null } {
    const box = query(root, `[data-testid=wellness-${key}]`);
    const value = (query(box, 'dd').textContent ?? '').replace(/\s+/g, ' ').trim();
    const trend = box.querySelector(`[data-testid=trend-${key}]`);
    return { value, trend: trend ? (trend.textContent ?? '').replace(/\s+/g, ' ').trim() : null };
  }

  it('shows the empty state when there is no summary', () => {
    const tile = show(null);

    expect(text(tile, '[data-testid=wellness-empty]')).toContain('Connect Intervals.icu');
    expect(tile.querySelector('[data-testid=wellness-warning]')).toBeNull();
    expect(tile.querySelector('[data-testid=wellness-sleep]')).toBeNull();
  });

  it('formats each metric with its unit and its trend against the usual', () => {
    const tile = show(FULL);

    expect(lines(tile, 'sleep')).toEqual({
      value: '7 h 30 min',
      trend: '↓ Down, 8 h 20 min usual',
    });
    expect(lines(tile, 'hrv')).toEqual({ value: '55.0 ms', trend: '↑ Up, 50.0 usual' });
    expect(lines(tile, 'resting_hr')).toEqual({ value: '54 bpm', trend: '↑ Up, 50 usual' });
    expect(lines(tile, 'weight')).toEqual({ value: '72.5 kg', trend: '→ Flat, 72.5 usual' });
  });

  it('shows a missing metric without a value or trend', () => {
    const tile = show({ ...FULL, hrv: { recent: null, baseline: null, trend: null } });

    expect(text(tile, '[data-testid=missing-hrv]')).toBe('No recent hrv');
    expect(
      query(tile, '[data-testid=wellness-hrv]').querySelector('[data-testid=trend-hrv]'),
    ).toBeNull();
  });

  it('shows no trend line when a metric has no baseline', () => {
    const tile = show({ ...FULL, sleep: { recent: 450, baseline: null, trend: null } });

    expect(tile.querySelector('[data-testid=trend-sleep]')).toBeNull();
  });

  it('hides the warning when recovery is not clearly worse', () => {
    const tile = show({ ...FULL, warning: false, warning_signals: [] });

    expect(tile.querySelector('[data-testid=wellness-warning]')).toBeNull();
  });

  it('names each metric that is worse than usual in the warning banner', () => {
    const tile = show(FULL);

    expect(text(tile, '[data-testid=wellness-warning-text]')).toBe(
      'Your sleep is shorter than usual and resting heart rate is higher than usual.',
    );
    expect(query(tile, '[data-testid=wellness-warning]').getAttribute('role')).toBe('alert');
  });

  it('names a single warning signal on its own', () => {
    const tile = show({ ...FULL, warning_signals: ['low_hrv'] });

    expect(text(tile, '[data-testid=wellness-warning-text]')).toBe('Your HRV is lower than usual.');
  });

  it('says something when the server warns without naming a signal', () => {
    const tile = show({ ...FULL, warning_signals: [] });

    expect(text(tile, '[data-testid=wellness-warning-text]')).toBe(
      'Your recovery is worse than usual.',
    );
  });
});
