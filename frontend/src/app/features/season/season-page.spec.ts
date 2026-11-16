import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { SeasonApi } from '../../core/season/season-api';
import { GetSeasonResult, Season, SeasonRace, SeasonWeek } from '../../core/season/season-models';
import { query, settle } from '../../testing/dom';
import { SeasonPage } from './season-page';

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
    week({ week_start: '2026-11-23', recovery: true, target_minutes: 156 }),
    week({
      week_start: '2026-11-30',
      phase: 'specific',
      target_minutes: 300,
      races: [{ ...MAIN, priority: 'preparation', title: 'Park run', distance_m: 5000 }],
    }),
    week({ week_start: '2026-12-07', phase: 'taper', target_minutes: 135, races: [MAIN] }),
  ],
};
const ROLLING: Season = {
  ...SEASON,
  rolling: true,
  main_race: null,
  weeks: [week(), week({ week_start: '2026-11-23', phase: 'build' })],
};

describe('SeasonPage', () => {
  let fixture: ComponentFixture<SeasonPage>;
  let page: HTMLElement;
  let get: ReturnType<typeof vi.fn<() => Promise<GetSeasonResult>>>;

  async function setup(first: GetSeasonResult | Error = { kind: 'ok', season: SEASON }) {
    get = vi.fn<() => Promise<GetSeasonResult>>();
    if (first instanceof Error) {
      get.mockRejectedValueOnce(first);
      get.mockResolvedValue({ kind: 'ok', season: SEASON });
    } else {
      get.mockResolvedValue(first);
    }
    TestBed.configureTestingModule({
      imports: [SeasonPage],
      providers: [provideRouter([]), { provide: SeasonApi, useValue: { get } }],
    });
    fixture = TestBed.createComponent(SeasonPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const rows = () => Array.from(page.querySelectorAll('tbody tr'));
  const cells = (index: number) =>
    Array.from(rows()[index].querySelectorAll('th, td')).map((cell) =>
      cell.textContent?.replace(/\s+/g, ' ').trim(),
    );
  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ');

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      get = vi
        .fn<() => Promise<GetSeasonResult>>()
        .mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [SeasonPage],
        providers: [provideRouter([]), { provide: SeasonApi, useValue: { get } }],
      });
      fixture = TestBed.createComponent(SeasonPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('table')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the season cannot be loaded', async () => {
      await setup(new Error('offline'));
      expect(text()).toContain('Your season could not be loaded.');

      query<HTMLButtonElement>(page, 'button.primary').click();
      await settle(fixture);

      expect(rows()).toHaveLength(4);
      expect(page.querySelector('[role="alert"]')).toBeNull();
    });

    it('says when the session is gone', async () => {
      await setup({ kind: 'forbidden' });

      expect(text()).toContain('Your session has ended.');
      expect(page.querySelector('table')).toBeNull();
    });
  });

  describe('a season with a race', () => {
    beforeEach(() => setup());

    it('names the main race, its day and the highest week', () => {
      const summary = query(page, '[data-testid="main-race"]').textContent?.replace(/\s+/g, ' ');

      expect(summary).toContain('A · Berlin Marathon · 42.2 km');
      expect(summary).toContain('Sun 28 Feb');
      expect(query(page, '[data-testid="peak"]').textContent).toBe('5 h');
    });

    it('has a row for every week with the week, the phase, the aim, the offer and the races', () => {
      expect(rows()).toHaveLength(4);
      expect(cells(0)).toEqual(['16 Nov – 22 Nov', 'Base', '4 h', '5 h', '']);
      expect(cells(3)).toEqual([
        '7 Dec – 13 Dec',
        'Taper',
        '2 h 15 min',
        '5 h',
        'A · Berlin Marathon · 42.2 km',
      ]);
    });

    it('marks a recovery week', () => {
      expect(cells(1)[1]).toBe('Base Recovery');
      expect(rows()[1].getAttribute('data-recovery')).toBe('true');
      expect(rows()[0].querySelector('[data-testid="recovery"]')).toBeNull();
    });

    it('shows a C race with its letter in its week', () => {
      expect(cells(2)[4]).toBe('C · Park run · 5 km');
    });

    it('says what the phases that occur are for, and only those', () => {
      const terms = Array.from(page.querySelectorAll('dt')).map((dt) => dt.textContent);

      expect(terms).toEqual(['Base', 'Specific', 'Taper']);
      expect(text()).toContain('Less volume, the intensity stays');
    });

    it('says that nothing is saved and that the numbers are a starting point', () => {
      expect(text()).toContain('worked out again every time you open this page; nothing is saved');
      expect(text()).toContain('The numbers are a starting point.');
    });

    it('says nothing about a missing race or a cut-off season', () => {
      expect(page.querySelector('[data-testid="no-race"]')).toBeNull();
      expect(page.querySelector('[data-testid="truncated"]')).toBeNull();
    });
  });

  describe('a season without a race', () => {
    beforeEach(() => setup({ kind: 'ok', season: ROLLING }));

    it('says so and points to the goals', () => {
      const note = query(page, '[data-testid="no-race"]');

      expect(note.textContent?.replace(/\s+/g, ' ')).toContain(
        'rolling skeleton of the next 2 weeks',
      );
      expect(query(note, 'a').getAttribute('href')).toBe('/goals');
      expect(page.querySelector('[data-testid="main-race"]')).toBeNull();
    });

    it('still lists the weeks', () => {
      expect(rows()).toHaveLength(2);
      expect(cells(1)[1]).toBe('Build');
    });
  });

  describe('a season that is cut off', () => {
    it('says that the last race lies more than a year away', async () => {
      await setup({ kind: 'ok', season: { ...SEASON, truncated: true } });

      expect(query(page, '[data-testid="truncated"]').textContent?.replace(/\s+/g, ' ')).toContain(
        'more than a year away. The skeleton stops after 4 weeks.',
      );
    });
  });

  describe('a week that offers nothing', () => {
    it('shows an aim and an offer of 0 min', async () => {
      await setup({
        kind: 'ok',
        season: { ...SEASON, weeks: [week({ target_minutes: 0, capacity_minutes: 0 })] },
      });

      expect(cells(0).slice(2, 4)).toEqual(['0 min', '0 min']);
    });
  });
});
