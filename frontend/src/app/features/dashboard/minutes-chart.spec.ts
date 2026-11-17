import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WeekMinutes } from '../../core/dashboard/dashboard-models';
import { query } from '../../testing/dom';
import { BAR_WIDTH, LEFT, MinutesChart, PLOT_HEIGHT, TOP, minutesLayout } from './minutes-chart';

const WEEKS: WeekMinutes[] = [
  { week_start: '2026-10-26', sports: [] },
  {
    week_start: '2026-11-02',
    sports: [
      { sport: 'running', minutes: 120 },
      { sport: 'cycling', minutes: 60 },
    ],
  },
  { week_start: '2026-11-09', sports: [{ sport: 'other', minutes: 30 }] },
];

describe('minutesLayout', () => {
  it('draws one bar per week, in the order given', () => {
    const layout = minutesLayout(WEEKS);

    expect(layout.bars.map((bar) => bar.week_start)).toEqual(WEEKS.map((week) => week.week_start));
    expect(layout.bars.map((bar) => bar.total)).toEqual([0, 180, 30]);
  });

  it('scales every bar on one axis that holds the highest', () => {
    const layout = minutesLayout(WEEKS);

    const [, high, low] = layout.bars;
    const bottom = TOP + PLOT_HEIGHT;
    const height = (bar: typeof high): number =>
      bar.segments.reduce((total, part) => total + part.height, 0);
    // 180 minutes are 3 h: the axis ends there, on a round number of hours
    expect(layout.ticks.map((tick) => tick.label)).toEqual(['0 h', '1 h', '2 h', '3 h']);
    expect(height(high)).toBeCloseTo(PLOT_HEIGHT);
    expect(height(low)).toBeCloseTo((30 / 180) * PLOT_HEIGHT);
    expect(layout.ticks[0].y).toBe(bottom);
  });

  it('stacks the sports in the order of the season chart, the first at the bottom', () => {
    const [, high] = minutesLayout(WEEKS).bars;

    expect(high.segments.map((part) => part.sport)).toEqual(['running', 'cycling']);
    expect(high.segments[0].y + high.segments[0].height).toBeCloseTo(TOP + PLOT_HEIGHT);
    expect(high.segments[1].y + high.segments[1].height).toBeCloseTo(high.segments[0].y);
  });

  it('gives a bar the numbers as text', () => {
    const layout = minutesLayout(WEEKS);

    expect(layout.bars[1].label).toBe('2 Nov – 8 Nov · Running 2 h · Cycling 1 h · 3 h in all');
    expect(layout.bars[0].label).toBe('26 Oct – 1 Nov · nothing done');
    expect(layout.bars[1].segments[0].label).toBe('Running 2 h');
  });

  it('lists the sports that occur, and only those', () => {
    expect(minutesLayout(WEEKS).sports).toEqual(['running', 'cycling', 'other']);
    expect(minutesLayout([{ week_start: '2026-11-09', sports: [] }]).sports).toEqual([]);
  });

  it('keeps every bar inside the picture and apart from the next', () => {
    const layout = minutesLayout(WEEKS);

    expect(layout.bars[0].x).toBeGreaterThanOrEqual(LEFT);
    const [first, second] = layout.bars;
    expect(second.x - first.x).toBeGreaterThan(BAR_WIDTH);
    expect(layout.bars[2].x + BAR_WIDTH).toBeLessThanOrEqual(layout.width);
  });

  it('labels every week with the day it starts', () => {
    expect(minutesLayout(WEEKS).labels.map((item) => item.text)).toEqual([
      '26 Oct',
      '2 Nov',
      '9 Nov',
    ]);
  });

  it('has an axis even without any minutes, and does not divide by zero', () => {
    const layout = minutesLayout([{ week_start: '2026-11-09', sports: [] }]);

    expect(layout.ticks.map((tick) => tick.label)).toEqual(['0 h', '1 h']);
    expect(layout.bars[0].segments).toEqual([]);
    expect(minutesLayout([]).bars).toEqual([]);
  });
});

describe('MinutesChart', () => {
  let fixture: ComponentFixture<MinutesChart>;

  function show(weeks: readonly WeekMinutes[]): HTMLElement {
    fixture = TestBed.createComponent(MinutesChart);
    fixture.componentRef.setInput('weeks', weeks);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  it('draws a picture that is named, with a bar for every week', () => {
    const chart = show(WEEKS);

    const svg = query(chart, '[data-testid=chart]');
    expect(svg.getAttribute('role')).toBe('img');
    expect(svg.getAttribute('aria-label')).toContain('minutes done');
    expect(svg.querySelectorAll('g[data-testid^=bar-]')).toHaveLength(3);
    expect(svg.querySelectorAll('rect')).toHaveLength(3);
  });

  it('gives every bar and part its numbers as a title', () => {
    const chart = show(WEEKS);

    const bar = query(chart, '[data-testid=bar-2026-11-02]');
    expect(bar.querySelector(':scope > title')?.textContent).toContain('3 h in all');
    expect(
      Array.from(bar.querySelectorAll('rect > title')).map((title) => title.textContent),
    ).toEqual(['Running 2 h', 'Cycling 1 h']);
  });

  it('colours the parts by sport and names the colours in a legend', () => {
    const chart = show(WEEKS);

    expect(query(chart, 'rect[data-sport=running]').classList).toContain('fill-sport-running');
    const legend = Array.from(chart.querySelectorAll('ul li')).map((li) =>
      (li.textContent ?? '').trim(),
    );
    expect(legend).toEqual(['Running', 'Cycling', 'Other']);
  });

  it('scales to the width of its place', () => {
    const chart = show(WEEKS);

    const svg = query(chart, '[data-testid=chart]');
    expect(svg.getAttribute('viewBox')).toMatch(/^0 0 320 \d+$/);
    expect(svg.getAttribute('width')).toBeNull();
    expect(svg.classList).toContain('w-full');
  });

  it('follows the weeks it is given', () => {
    const chart = show(WEEKS);

    fixture.componentRef.setInput('weeks', [WEEKS[2]]);
    fixture.detectChanges();

    expect(chart.querySelectorAll('g[data-testid^=bar-]')).toHaveLength(1);
  });
});
