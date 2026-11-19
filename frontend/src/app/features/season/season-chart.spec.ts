import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Season, SeasonPlan, SeasonWeek } from '../../core/season/season-models';
import { query } from '../../testing/dom';
import {
  BAR_GAP,
  BAR_WIDTH,
  DONE_GAP,
  DONE_WIDTH,
  LEFT,
  PLOT_HEIGHT,
  SeasonChart,
  TOP,
  chartLayout,
  chartWeeks,
  niceAxis,
  niceLoadAxis,
} from './season-chart';

function week(start: string, target = 300): SeasonWeek {
  return {
    week_start: start,
    phase: 'base',
    recovery: false,
    target_minutes: target,
    capacity_minutes: 600,
    races: [],
  };
}

const SEASON: Season = {
  rolling: true,
  truncated: false,
  main_race: null,
  peak_minutes: 300,
  weeks: [week('2026-11-16', 240), week('2026-11-23', 120), week('2026-11-30', 0)],
};

function planOf(minutes: Record<string, number>[]): SeasonPlan {
  return {
    id: '0195f3a0-0000-7000-8000-000000000001',
    version: 1,
    status: 'confirmed',
    reason: '',
    request: '',
    rationale: '',
    parent: null,
    created_at: '2026-11-16T10:00:00Z',
    confirmed_at: '2026-11-16T10:00:00Z',
    skeleton: SEASON,
    weeks: minutes.map((entry, index) => ({
      week_start: SEASON.weeks[index].week_start,
      minutes: entry,
      total_minutes: Object.values(entry).reduce((sum, value) => sum + value, 0),
      planned_load: { running: 80, cycling: 40 },
      total_planned_load: 120,
      focus: 'endurance',
      key_sessions: [],
      reason: '',
      done: null,
      done_load: null,
    })),
    report: null,
  };
}

describe('niceAxis', () => {
  it.each([
    [0, 1, 60],
    [60, 1, 60],
    [61, 1, 120],
    [300, 1, 300],
    [361, 2, 480],
    [600, 2, 600],
    [1500, 5, 1500],
    [3600, 10, 3600],
  ])('holds %i minutes with a step of %i h to %i minutes', (highest, step, top) => {
    expect(niceAxis(highest)).toEqual({ step, maxMinutes: top });
  });

  it('has at most six steps', () => {
    for (const minutes of [1, 59, 100, 777, 1234, 5000, 20000]) {
      const { step, maxMinutes } = niceAxis(minutes);

      expect(maxMinutes).toBeGreaterThanOrEqual(minutes);
      expect(maxMinutes / 60 / step).toBeLessThanOrEqual(6);
    }
  });
});

describe('niceLoadAxis', () => {
  it.each([
    [0, 1, 1],
    [1, 1, 1],
    [6, 1, 6],
    [7, 2, 8],
    [120, 20, 120],
    [301, 100, 400],
    [601, 200, 800],
    [4000, 1000, 4000],
    [20000, 5000, 20000],
  ])('holds %i load points with a step of %i to %i', (highest, step, maxLoad) => {
    expect(niceLoadAxis(highest)).toEqual({ step, maxLoad });
    expect(maxLoad).toBeGreaterThanOrEqual(highest);
    expect(maxLoad / step).toBeLessThanOrEqual(6);
  });
});

describe('chartWeeks', () => {
  it('takes the aim of the skeleton when there is no plan', () => {
    expect(chartWeeks(SEASON, null).map((w) => w.planned)).toEqual([
      { aim: 240 },
      { aim: 120 },
      { aim: 0 },
    ]);
  });

  it('takes the minutes of the plan by sport when there is one', () => {
    const plan = planOf([{ running: 100, cycling: 50 }, { running: 60 }, {}]);

    expect(chartWeeks(SEASON, plan).map((w) => w.planned)).toEqual([
      { running: 100, cycling: 50 },
      { running: 60 },
      {},
    ]);
  });

  it('uses server load estimates and keeps unknown and empty done load distinct', () => {
    const plan = planOf([{ running: 100 }, { running: 60 }, {}]);
    plan.weeks[0].done_load = [{ sport: 'other', load: 170 }];
    plan.weeks[1].done_load = [];

    expect(chartWeeks(SEASON, plan, 'load')).toEqual([
      { week_start: '2026-11-16', planned: { running: 80, cycling: 40 }, done: { other: 170 } },
      { week_start: '2026-11-23', planned: { running: 80, cycling: 40 }, done: {} },
      { week_start: '2026-11-30', planned: { running: 80, cycling: 40 }, done: null },
    ]);
    expect(
      chartWeeks(SEASON, null, 'load').every((week) => Object.keys(week.planned).length === 0),
    ).toBe(true);
  });
});

describe('load chart layout', () => {
  const weeks = [
    {
      week_start: '2026-11-16',
      planned: { strength: 20, swimming: 20, cycling: 40, running: 40 },
      done: { other: 80, running: 120 },
    },
    { week_start: '2026-11-23', planned: {}, done: {} },
    { week_start: '2026-11-30', planned: {}, done: null },
  ];
  const layout = chartLayout(weeks, 'load');

  it('scales both stacks to a common load axis that includes the highest done total', () => {
    expect(layout.maxValue).toBe(200);
    expect(layout.ticks[0]).toEqual({ y: TOP + PLOT_HEIGHT, label: '0 pts' });
    expect(layout.ticks.at(-1)).toEqual({ y: TOP, label: '200 pts' });
    expect(layout.bars[0].segments.reduce((sum, part) => sum + part.height, 0)).toBeCloseTo(
      (PLOT_HEIGHT * 120) / 200,
    );
    expect(layout.bars[0].done?.segments.reduce((sum, part) => sum + part.height, 0)).toBeCloseTo(
      PLOT_HEIGHT,
    );
    expect(layout.left).toBeGreaterThan(LEFT);
  });

  it('stacks sports in the same order and aligns the narrower done bars', () => {
    const first = layout.bars[0];
    expect(first.segments.map((part) => part.series)).toEqual([
      'running',
      'cycling',
      'swimming',
      'strength',
    ]);
    expect(first.done?.segments.map((part) => part.series)).toEqual(['running', 'other']);
    expect(first.segments[0].y + first.segments[0].height).toBeCloseTo(TOP + PLOT_HEIGHT);
    expect(first.segments[1].y + first.segments[1].height).toBeCloseTo(first.segments[0].y);
    expect(first.done?.x).toBe(first.x + BAR_WIDTH + DONE_GAP);
    expect(first.done?.width).toBe(DONE_WIDTH);
    expect(layout.bars[1].x - first.x).toBe(BAR_WIDTH + DONE_GAP + DONE_WIDTH + BAR_GAP);
    expect(layout.series).toEqual(['running', 'cycling', 'swimming', 'strength', 'other']);
  });

  it('labels planned and done load per sport and in total without hour units', () => {
    expect(layout.bars[0].label).toBe(
      '16 Nov – 22 Nov · Planned: Running 40 pts · Planned: Cycling 40 pts · Planned: Swimming 20 pts · Planned: Strength 20 pts · 120 pts planned · Done: Running 120 pts · Done: Other 80 pts · 200 pts done',
    );
    expect(layout.bars[1].label).toContain('nothing planned · nothing done');
    expect(layout.bars[1].done?.segments).toEqual([]);
    expect(layout.bars[2].done).toBeNull();
    expect(layout.bars[2].label).not.toContain('done');
  });

  it('has a finite scale and no segments for zero load', () => {
    const empty = chartLayout([{ week_start: '2026-11-16', planned: {} }], 'load');
    expect(empty.maxValue).toBe(1);
    expect(empty.bars[0].segments).toEqual([]);
    expect(empty.ticks.every((tick) => Number.isFinite(tick.y))).toBe(true);
  });
});

describe('chartLayout', () => {
  const layout = chartLayout(
    chartWeeks(SEASON, planOf([{ running: 100, cycling: 140 }, { swimming: 120 }, {}])),
  );

  it('has a bar for every week, side by side', () => {
    expect(layout.bars.map((bar) => bar.x)).toEqual([
      LEFT,
      LEFT + BAR_WIDTH + BAR_GAP,
      LEFT + 2 * (BAR_WIDTH + BAR_GAP),
    ]);
    expect(layout.bars.map((bar) => bar.week_start)).toEqual(SEASON.weeks.map((w) => w.week_start));
  });

  it('puts the highest bar on a round axis and sizes the others in proportion', () => {
    expect(layout.maxValue).toBe(240);
    expect(layout.bars[0].segments.reduce((sum, s) => sum + s.height, 0)).toBeCloseTo(PLOT_HEIGHT);
    expect(layout.bars[1].segments[0].height).toBeCloseTo(PLOT_HEIGHT / 2);
  });

  it('stacks the sports from the bottom in a fixed order', () => {
    const [running, cycling] = layout.bars[0].segments;

    expect(running.series).toBe('running');
    expect(cycling.series).toBe('cycling');
    expect(running.y + running.height).toBeCloseTo(TOP + PLOT_HEIGHT);
    expect(cycling.y + cycling.height).toBeCloseTo(running.y);
  });

  it('draws no part for a week without minutes', () => {
    expect(layout.bars[2].segments).toEqual([]);
    expect(layout.bars[2].label).toContain('nothing planned');
  });

  it('lists only the series that occur, in the order of the stack', () => {
    expect(layout.series).toEqual(['running', 'cycling', 'swimming']);
  });

  it('writes the numbers of a bar as text', () => {
    expect(layout.bars[0].label).toBe(
      '16 Nov – 22 Nov · Running 1 h 40 min · Cycling 2 h 20 min · 4 h planned',
    );
    expect(layout.bars[0].segments[1].label).toBe('Cycling 2 h 20 min');
  });

  it('has a tick for every step of the hour axis, from the bottom', () => {
    expect(layout.ticks[0]).toEqual({ y: TOP + PLOT_HEIGHT, label: '0 h' });
    expect(layout.ticks.at(-1)).toEqual({ y: TOP, label: '4 h' });
  });

  it('is as wide as its weeks need', () => {
    const wide = chartLayout(
      Array.from({ length: 52 }, (_, n) => ({ week_start: `2026-${n}`, planned: { running: 60 } })),
    );

    expect(wide.width).toBeGreaterThan(52 * (BAR_WIDTH + BAR_GAP));
    expect(wide.bars).toHaveLength(52);
  });

  it('labels every fourth week', () => {
    const weeks = Array.from({ length: 9 }, (_, n) => ({
      week_start: `2026-11-${String(16 + 7 * n).padStart(2, '0')}`,
      planned: { running: 60 },
    })).slice(0, 2);

    expect(chartLayout(weeks).labels.map((label) => label.text)).toEqual(['16 Nov']);
  });

  it('has an axis of one hour for a season without minutes', () => {
    const empty = chartLayout([{ week_start: '2026-11-16', planned: {} }]);

    expect(empty.maxValue).toBe(60);
    expect(empty.bars[0].segments).toEqual([]);
  });

  describe('with the minutes done', () => {
    const weeks = chartWeeks(
      SEASON,
      (() => {
        const plan = planOf([{ running: 100 }, { running: 60 }, {}]);
        plan.weeks[0].done = [
          { sport: 'running', minutes: 80 },
          { sport: 'other', minutes: 30 },
        ];
        plan.weeks[1].done = [];
        return plan;
      })(),
    );
    const done = chartLayout(weeks);

    it('has a second, narrower bar right beside the plan for the weeks that have them', () => {
      const [first, second, third] = done.bars;

      expect(first.done?.width).toBe(DONE_WIDTH);
      expect(first.done?.x).toBe(first.x + BAR_WIDTH + DONE_GAP);
      expect(second.done?.segments).toEqual([]);
      expect(third.done).toBeNull();
      expect(done.withDone).toBe(true);
    });

    it('stacks the sports done like the plan, with other on top', () => {
      expect(done.bars[0].done?.segments.map((s) => s.series)).toEqual(['running', 'other']);
      expect(done.bars[0].done?.total).toBe(110);
    });

    it('takes the minutes done into account for the axis', () => {
      const more = chartLayout([
        { week_start: '2026-11-16', planned: { running: 60 }, done: { running: 400 } },
      ]);

      expect(more.maxValue).toBe(480);
      expect(more.bars[0].done?.segments[0].height).toBeLessThanOrEqual(PLOT_HEIGHT);
    });

    it('gives every week the room for the second bar so that the bars line up', () => {
      expect(done.bars[1].x - done.bars[0].x).toBe(BAR_WIDTH + DONE_GAP + DONE_WIDTH + BAR_GAP);
    });

    it('says in the label what was done, and when nothing was', () => {
      expect(done.bars[0].label).toBe(
        '16 Nov – 22 Nov · Running 1 h 40 min · 1 h 40 min planned · 1 h 50 min done',
      );
      expect(done.bars[1].label).toContain('nothing done');
      expect(done.bars[2].label).not.toContain('done');
    });

    it('marks the segments of the bar done as done', () => {
      expect(done.bars[0].done?.segments[1].label).toBe('Done: Other 30 min');
    });

    it('lists the series done in the legend as well', () => {
      expect(done.series).toEqual(['running', 'other']);
    });

    it('has no second bar anywhere without minutes done', () => {
      const plain = chartLayout(chartWeeks(SEASON, null));

      expect(plain.withDone).toBe(false);
      expect(plain.bars.every((bar) => bar.done === null)).toBe(true);
    });
  });

  it('is the same picture for the same weeks', () => {
    const weeks = chartWeeks(SEASON, null);

    expect(chartLayout(weeks)).toEqual(chartLayout(weeks));
  });
});

describe('SeasonChart', () => {
  let fixture: ComponentFixture<SeasonChart>;
  let host: HTMLElement;

  async function render(season: Season, plan: SeasonPlan | null = null) {
    fixture = TestBed.createComponent(SeasonChart);
    fixture.componentRef.setInput('season', season);
    fixture.componentRef.setInput('plan', plan);
    host = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  const rects = () => Array.from(host.querySelectorAll('rect'));

  it('draws the aim of the skeleton without a plan', async () => {
    await render(SEASON);

    expect(rects().map((rect) => rect.getAttribute('data-series'))).toEqual(['aim', 'aim']);
    expect(host.querySelector('svg')?.getAttribute('aria-label')).toContain('skeleton aims for');
    expect(host.querySelector('[data-testid="chart-load"]')).toBeNull();
  });

  it('draws the plan by sport with a legend for the colours that occur', async () => {
    await render(SEASON, planOf([{ running: 100, cycling: 50 }, { running: 60 }, {}]));

    expect(rects().map((rect) => rect.getAttribute('data-series'))).toEqual([
      'running',
      'cycling',
      'running',
    ]);
    expect(
      Array.from(host.querySelectorAll('.legend li')).map((li) => li.textContent?.trim()),
    ).toEqual(['Running', 'Cycling']);
    expect(host.querySelector('svg')?.getAttribute('aria-label')).toContain('planned');
  });

  it('has the numbers of every bar and part as text', async () => {
    await render(SEASON, planOf([{ running: 100 }, {}, {}]));

    expect(host.querySelector('[data-testid="bar-2026-11-16"] > title')?.textContent).toContain(
      '1 h 40 min planned',
    );
    expect(host.querySelector('rect > title')?.textContent).toBe('Running 1 h 40 min');
  });

  it('draws the minutes done as narrow bars and explains them in the legend', async () => {
    const plan = planOf([{ running: 100 }, { running: 60 }, {}]);
    plan.weeks[0].done = [{ sport: 'running', minutes: 80 }];
    await render(SEASON, plan);

    expect(host.querySelectorAll('rect.done')).toHaveLength(1);
    expect(host.querySelector('rect.done > title')?.textContent).toBe('Done: Running 1 h 20 min');
    expect(host.querySelector('[data-testid="legend-done"]')?.textContent).toContain('narrow bar');
  });

  it('has no legend for the minutes done when there are none', async () => {
    await render(SEASON, planOf([{ running: 100 }, {}, {}]));

    expect(host.querySelector('[data-testid="legend-done"]')).toBeNull();
    expect(host.querySelector('rect.done')).toBeNull();
  });

  it('toggles minutes and load, including sport tooltips, axis labels and accessible selection', async () => {
    const plan = planOf([{ running: 100 }, { running: 60 }, {}]);
    plan.weeks[0].done = [{ sport: 'running', minutes: 60 }];
    plan.weeks[0].done_load = [{ sport: 'other', load: 170 }];
    await render(SEASON, plan);
    const minutes = query<HTMLButtonElement>(host, '[data-testid="chart-minutes"]');
    const load = query<HTMLButtonElement>(host, '[data-testid="chart-load"]');
    expect(minutes.getAttribute('aria-pressed')).toBe('true');
    expect(load.getAttribute('aria-pressed')).toBe('false');

    load.click();
    await fixture.whenStable();

    expect(load.getAttribute('aria-pressed')).toBe('true');
    expect(minutes.getAttribute('aria-pressed')).toBe('false');
    expect(host.querySelector('svg')?.getAttribute('aria-label')).toContain('load points');
    expect(host.querySelector('rect > title')?.textContent).toBe('Planned: Running 80 pts');
    expect(host.querySelector('rect.done > title')?.textContent).toBe('Done: Other 170 pts');
    expect(host.querySelector('[data-testid="bar-2026-11-16"] > title')?.textContent).toContain(
      '120 pts planned · Done: Other 170 pts · 170 pts done',
    );
    expect(host.querySelector('.axis')?.textContent?.trim()).toBe('0 pts');
    expect(host.querySelector('.legend')?.textContent).toContain('Other');

    minutes.click();
    await fixture.whenStable();

    expect(host.querySelector('rect > title')?.textContent).toBe('Running 1 h 40 min');
    expect(host.querySelector('rect.done > title')?.textContent).toBe('Done: Running 1 h');
    expect(host.querySelector('.axis')?.textContent?.trim()).toBe('0 h');
    expect(minutes.getAttribute('aria-pressed')).toBe('true');
  });

  it('updates load for a different version and falls back to minutes for the skeleton', async () => {
    await render(SEASON, planOf([{ running: 100 }, {}, {}]));
    query<HTMLButtonElement>(host, '[data-testid="chart-load"]').click();
    await fixture.whenStable();
    const draft = planOf([{ running: 60 }, {}, {}]);
    draft.status = 'draft';
    draft.weeks[0].planned_load = { swimming: 50 };
    draft.weeks[0].total_planned_load = 50;
    fixture.componentRef.setInput('plan', draft);
    await fixture.whenStable();
    expect(host.querySelector('rect > title')?.textContent).toBe('Planned: Swimming 50 pts');
    expect(host.querySelector('rect.done')).toBeNull();

    fixture.componentRef.setInput('plan', null);
    await fixture.whenStable();
    expect(host.querySelector('rect > title')?.textContent).toBe('Aim of the skeleton 4 h');
    expect(host.querySelector('[data-testid="chart-load"]')).toBeNull();
  });

  it('draws nothing for a season without weeks', async () => {
    await render({ ...SEASON, weeks: [] });

    expect(host.querySelector('svg')).toBeNull();
  });
});
