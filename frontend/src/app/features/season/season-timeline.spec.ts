import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Season, SeasonRace, SeasonWeek } from '../../core/season/season-models';
import { SeasonTimeline, centeredScroll, timelineCells } from './season-timeline';

const MAIN: SeasonRace = {
  date: '2027-02-28',
  priority: 'main',
  discipline: 'running',
  distance_m: 42195,
  title: 'Berlin Marathon',
};

function week(changes: Partial<SeasonWeek> = {}): SeasonWeek {
  return {
    week_start: '2026-11-16',
    phase: 'base',
    recovery: false,
    target_minutes: 240,
    capacity_minutes: 300,
    races: [],
    ...changes,
  };
}

const SEASON: Season = {
  rolling: false,
  truncated: false,
  main_race: MAIN,
  peak_minutes: 300,
  weeks: [
    week(),
    week({ week_start: '2026-11-23', phase: 'build', recovery: true }),
    week({
      week_start: '2026-11-30',
      phase: 'specific',
      races: [{ ...MAIN, priority: 'preparation', title: 'Park run' }],
    }),
    week({ week_start: '2026-12-07', phase: 'taper', races: [MAIN] }),
    week({ week_start: '2026-12-14', phase: 'transition' }),
  ],
};

describe('timelineCells', () => {
  it('has one cell for every week, in order', () => {
    const cells = timelineCells(SEASON, '2026-11-01');

    expect(cells.map((cell) => cell.week_start)).toEqual(SEASON.weeks.map((w) => w.week_start));
    expect(cells.map((cell) => cell.phase)).toEqual([
      'base',
      'build',
      'specific',
      'taper',
      'transition',
    ]);
  });

  it('writes the phase in two letters', () => {
    expect(timelineCells(SEASON, '2026-11-01').map((cell) => cell.abbreviation)).toEqual([
      'Ba',
      'Bu',
      'Sp',
      'Ta',
      'Tr',
    ]);
  });

  it('marks the recovery weeks', () => {
    expect(timelineCells(SEASON, '2026-11-01').map((cell) => cell.recovery)).toEqual([
      false,
      true,
      false,
      false,
      false,
    ]);
  });

  it('gives the races their letter and their title', () => {
    const cells = timelineCells(SEASON, '2026-11-01');

    expect(cells[2].races).toEqual([{ letter: 'C', title: 'Park run' }]);
    expect(cells[3].races).toEqual([{ letter: 'A', title: 'Berlin Marathon' }]);
    expect(cells[0].races).toEqual([]);
  });

  it.each([
    ['2026-11-16', 0],
    ['2026-11-22', 0],
    ['2026-11-23', 1],
    ['2026-12-20', 4],
  ])('marks the week of %s as the current one (cell %i)', (today, index) => {
    const cells = timelineCells(SEASON, today);

    expect(cells.map((cell) => cell.current)).toEqual(cells.map((_, i) => i === index));
  });

  it.each(['2026-11-15', '2026-12-21', '2030-01-01'])('marks none when today is %s', (today) => {
    expect(timelineCells(SEASON, today).some((cell) => cell.current)).toBe(false);
  });

  it('tells the whole story of a week in its label', () => {
    const cells = timelineCells(SEASON, '2026-11-24');

    expect(cells[1].label).toBe('23 Nov – 29 Nov · Build · Recovery week · This week');
    expect(cells[3].label).toBe('7 Dec – 13 Dec · Taper · A race Berlin Marathon');
  });

  it('has no cells for a season without weeks', () => {
    expect(timelineCells({ ...SEASON, weeks: [] }, '2026-11-16')).toEqual([]);
  });
});

describe('centeredScroll', () => {
  it('puts the cell in the middle of the row', () => {
    expect(centeredScroll(300, 500, 40)).toBe(370);
  });

  it('never scrolls before the start', () => {
    expect(centeredScroll(300, 20, 40)).toBe(0);
  });
});

describe('SeasonTimeline', () => {
  let fixture: ComponentFixture<SeasonTimeline>;
  let host: HTMLElement;

  async function render(season: Season, today = '2026-11-24') {
    fixture = TestBed.createComponent(SeasonTimeline);
    fixture.componentRef.setInput('season', season);
    fixture.componentRef.setInput('today', today);
    host = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  const cells = () => Array.from(host.querySelectorAll('[data-testid="timeline-cell"]'));

  it('draws a cell for every week with its phase', async () => {
    await render(SEASON);

    expect(cells().map((cell) => cell.getAttribute('data-phase'))).toEqual([
      'base',
      'build',
      'specific',
      'taper',
      'transition',
    ]);
    expect(cells().map((cell) => cell.querySelector('.phase')?.textContent)).toEqual([
      'Ba',
      'Bu',
      'Sp',
      'Ta',
      'Tr',
    ]);
  });

  it('marks the current week and the recovery week', async () => {
    await render(SEASON);

    expect(cells().map((cell) => cell.getAttribute('data-current'))).toEqual([
      null,
      'true',
      null,
      null,
      null,
    ]);
    expect(cells()[1].getAttribute('data-recovery')).toBe('true');
    expect(cells()[1].querySelector('.mark')?.textContent).toBe('R');
  });

  it('shows the letter of a race and the title only as text of the label', async () => {
    await render(SEASON);

    const races = Array.from(host.querySelectorAll('[data-testid="timeline-race"]'));
    expect(races.map((race) => race.textContent)).toEqual(['C', 'A']);
    expect(cells()[3].getAttribute('aria-label')).toContain('Berlin Marathon');
    expect(host.textContent).not.toContain('Berlin Marathon');
  });

  it('keeps a title that looks like markup as text', async () => {
    const hostile = '<img src=x onerror=alert(1)>';
    await render({
      ...SEASON,
      weeks: [week({ races: [{ ...MAIN, title: hostile }] })],
    });

    expect(host.querySelector('img')).toBeNull();
    expect(cells()[0].getAttribute('title')).toContain(hostile);
  });

  it('draws nothing for a season without weeks', async () => {
    await render({ ...SEASON, weeks: [] });

    expect(cells()).toEqual([]);
  });

  it('describes the list for a screen reader', async () => {
    await render(SEASON);

    expect(host.querySelector('ol')?.getAttribute('aria-label')).toBe(
      'The weeks of the season by phase',
    );
  });

  describe('the start position', () => {
    let scrolled: number | null;

    async function renderScrolled(today: string) {
      scrolled = null;
      fixture = TestBed.createComponent(SeasonTimeline);
      fixture.componentRef.setInput('season', SEASON);
      fixture.componentRef.setInput('today', today);
      host = fixture.nativeElement as HTMLElement;
      Object.defineProperty(host, 'scrollLeft', {
        configurable: true,
        get: () => 0,
        set: (value: number) => (scrolled = value),
      });
      await fixture.whenStable();
    }

    afterEach(() => vi.restoreAllMocks());

    it('moves the row so that this week is in the middle', async () => {
      vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(300);
      vi.spyOn(HTMLElement.prototype, 'offsetLeft', 'get').mockReturnValue(500);
      vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(40);

      await renderScrolled('2026-11-24');

      expect(scrolled).toBe(370);
    });

    it('leaves the row alone when no week of the season is this week', async () => {
      await renderScrolled('2030-01-01');

      expect(scrolled).toBeNull();
    });
  });
});
