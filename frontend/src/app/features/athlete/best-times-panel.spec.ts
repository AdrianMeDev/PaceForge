import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AthleteApi } from '../../core/athlete/athlete-api';
import {
  AthleteProfile,
  BestTime,
  BestTimeDistance,
  BestTimeInput,
  ClearBestTimeResult,
  SetBestTimeResult,
} from '../../core/athlete/athlete-models';
import { query, settle, typeInto } from '../../testing/dom';
import { BestTimesPanel } from './best-times-panel';

const NONE: AthleteProfile['best_times'] = {
  '5k': null,
  '10k': null,
  half_marathon: null,
  marathon: null,
};

const FIVE_K: BestTime = {
  seconds: 1197,
  date: '2026-10-03',
  vdot: 50,
  recent: true,
  counts: true,
};
const OLD_TEN: BestTime = {
  seconds: 2700,
  date: '2024-05-01',
  vdot: 45.8,
  recent: false,
  counts: false,
};

function profile(
  times: Partial<AthleteProfile['best_times']> = {},
  vdot: AthleteProfile['vdot'] = null,
): AthleteProfile {
  return {
    best_times: { ...NONE, ...times },
    vdot,
    birth_year: null,
    sex: null,
    weight_kg: null,
    resting_hr: null,
    training_years: { running: null, cycling: null, swimming: null, strength: null },
    strength_experience: null,
    strength_equipment: [],
    timezone: 'UTC',
    intervals: { connected: false, synced_at: null },
    sports: {
      ride: {
        thresholds: {
          ftp: { effective: null, candidates: [] },
          lthr: { effective: null, candidates: [] },
          max_hr: { effective: null, candidates: [] },
        },
        zones: { power: null, heart_rate: null },
      },
      run: {
        thresholds: {
          threshold_pace: { effective: null, candidates: [] },
          lthr: { effective: null, candidates: [] },
          max_hr: { effective: null, candidates: [] },
        },
        zones: { pace: null, heart_rate: null },
      },
    },
  };
}

const WITH_TIMES = profile(
  { '5k': FIVE_K, '10k': OLD_TEN },
  { value: 50, distance: '5k', date: '2026-10-03' },
);

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('BestTimesPanel', () => {
  let api: {
    setBestTime: ReturnType<
      typeof vi.fn<(d: BestTimeDistance, i: BestTimeInput) => Promise<SetBestTimeResult>>
    >;
    clearBestTime: ReturnType<typeof vi.fn<(d: BestTimeDistance) => Promise<ClearBestTimeResult>>>;
  };
  let fixture: ComponentFixture<BestTimesPanel>;
  let panel: HTMLElement;

  async function setup(start: AthleteProfile = profile()) {
    api = { setBestTime: vi.fn(), clearBestTime: vi.fn() };
    api.setBestTime.mockResolvedValue({ kind: 'ok', profile: WITH_TIMES });
    api.clearBestTime.mockResolvedValue({ kind: 'ok', profile: profile() });
    TestBed.configureTestingModule({
      imports: [BestTimesPanel],
      providers: [{ provide: AthleteApi, useValue: api }],
    });
    fixture = TestBed.createComponent(BestTimesPanel);
    fixture.componentRef.setInput('profile', start);
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const notice = () => panel.querySelector('[role="status"]')?.textContent?.trim();
  const value = (id: string) => query<HTMLInputElement>(panel, `#${id}`).value;
  const counting = () => query(panel, '[data-testid="counting"]').textContent?.replace(/\s+/g, ' ');
  const meta = (distance: string) =>
    query(panel, `[data-testid="best-${distance}"] [data-testid="meta"]`)
      .textContent?.replace(/\s+/g, ' ')
      .trim();

  async function type(id: string, text: string): Promise<void> {
    typeInto(panel, `#${id}`, text);
    await settle(fixture);
  }

  async function submit(distance: string): Promise<void> {
    query<HTMLFormElement>(panel, `[data-testid="best-${distance}"] form`).dispatchEvent(
      new Event('submit', { cancelable: true }),
    );
    await settle(fixture);
  }

  async function click(label: string): Promise<void> {
    query<HTMLButtonElement>(panel, `button[aria-label="${label}"]`).click();
    await settle(fixture);
  }

  describe('the rows as cards', () => {
    it('puts the time and the date of a row in a grid and keeps Save and Remove together', async () => {
      await setup();

      const row = query(panel, '[data-testid="best-5k"]');
      expect(row.querySelector('form.form-grid')).not.toBeNull();
      expect(row.querySelector('.actions button[type="submit"]')).not.toBeNull();
    });
  });

  describe('what is shown', () => {
    it('has a row for each distance, shortest first', async () => {
      await setup();

      expect(
        Array.from(panel.querySelectorAll('li h3')).map((heading) => heading.textContent),
      ).toEqual(['5 km', '10 km', 'Half marathon', 'Marathon']);
    });

    it('says that no time counts when there is none', async () => {
      await setup();

      expect(counting()).toContain('No best time counts yet.');
      expect(panel.querySelector('[data-testid="meta"]')).toBeNull();
    });

    it('shows the VDOT that counts and where it comes from', async () => {
      await setup(WITH_TIMES);

      expect(counting()).toContain('Your VDOT: 50 (from your 5 km on 2026-10-03)');
    });

    it('starts with the stored times and days', async () => {
      await setup(WITH_TIMES);

      expect(value('best-time-5k')).toBe('19:57');
      expect(value('best-date-5k')).toBe('2026-10-03');
      expect(value('best-time-10k')).toBe('45:00');
      expect(value('best-time-marathon')).toBe('');
    });

    it('says for each time what it means for the pace', async () => {
      await setup(WITH_TIMES);

      expect(meta('5k')).toBe('VDOT 50 · This one gives your threshold pace.');
      expect(meta('10k')).toBe('VDOT 45.8 · More than a year ago: too old to count.');
    });

    it('explains the model and says that the coach is told', async () => {
      await setup();

      const text = panel.textContent ?? '';
      expect(text).toContain('The VDOT is a model and a starting point');
      expect(text).toContain('Your AI coach is told the times and the VDOT.');
    });

    it('offers to remove only a time that is stored', async () => {
      await setup(WITH_TIMES);

      expect(panel.querySelector('button[aria-label="Remove the 5 km time"]')).not.toBeNull();
      expect(panel.querySelector('button[aria-label="Remove the Marathon time"]')).toBeNull();
    });
  });

  describe('saving', () => {
    beforeEach(() => setup());

    it('sends the time in seconds and the day, then tells the page and says so', async () => {
      const emitted: AthleteProfile[] = [];
      fixture.componentInstance.changed.subscribe((p) => emitted.push(p));
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');

      await submit('5k');

      expect(api.setBestTime).toHaveBeenCalledExactlyOnceWith('5k', {
        seconds: 1197,
        date: '2026-10-03',
      });
      expect(notice()).toBe('Saved.');
      expect(emitted).toEqual([WITH_TIMES]);
    });

    it('shows what the server stored in the row that was saved, and leaves the others', async () => {
      await type('best-time-marathon', '3:30:00');
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');

      await submit('5k');

      expect(value('best-time-5k')).toBe('19:57');
      expect(value('best-time-marathon')).toBe('3:30:00');
    });

    it('does not ask the server for a time or a day that cannot be used, and names them', async () => {
      await type('best-time-5k', 'fast');

      await submit('5k');

      expect(api.setBestTime).not.toHaveBeenCalled();
      expect(alerts()).toEqual([
        'Enter the time as hours, minutes and seconds, for example 3:45:00.',
        'Enter the day of the race.',
      ]);
      expect(query(panel, '#best-time-5k').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows the server’s messages next to their fields', async () => {
      await type('best-time-5k', '5:00');
      await type('best-date-5k', '2026-10-03');
      api.setBestTime.mockResolvedValue({
        kind: 'invalid',
        errors: ['Not plausible.'],
        fields: { seconds: ['Not plausible.'] },
      });

      await submit('5k');

      expect(alerts()).toEqual(['Not plausible.']);
      expect(query(panel, '#best-time-5k').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message that no field owns above the list', async () => {
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');
      api.setBestTime.mockResolvedValue({
        kind: 'invalid',
        errors: ['Something general.'],
        fields: { non_field_errors: ['Something general.'] },
      });

      await submit('5k');

      expect(alerts()).toEqual(['Something general.']);
    });

    it('says when the distance does not exist', async () => {
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');
      api.setBestTime.mockResolvedValue({ kind: 'not_found' });

      await submit('5k');

      expect(alerts()).toEqual(['That distance does not exist any more.']);
    });

    it('says something went wrong when the request fails', async () => {
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');
      api.setBestTime.mockRejectedValue(new Error('offline'));

      await submit('5k');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('tells the page when the session is gone', async () => {
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');
      api.setBestTime.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await submit('5k');

      expect(gone).toBe(1);
    });

    it('does one thing at a time', async () => {
      await type('best-time-5k', '19:57');
      await type('best-date-5k', '2026-10-03');
      const slow = deferred<SetBestTimeResult>();
      api.setBestTime.mockReturnValue(slow.promise);

      void submit('5k');
      await settle(fixture);
      await submit('5k');

      expect(api.setBestTime).toHaveBeenCalledTimes(1);
      slow.resolve({ kind: 'ok', profile: WITH_TIMES });
      await settle(fixture);
    });
  });

  describe('removing', () => {
    beforeEach(() => setup(WITH_TIMES));

    it('removes the time, empties its row and tells the page', async () => {
      const emitted: AthleteProfile[] = [];
      fixture.componentInstance.changed.subscribe((p) => emitted.push(p));

      await click('Remove the 5 km time');

      expect(api.clearBestTime).toHaveBeenCalledExactlyOnceWith('5k');
      expect(notice()).toBe('Removed.');
      expect(value('best-time-5k')).toBe('');
      expect(emitted).toHaveLength(1);
    });

    it('tells the page when the session is gone', async () => {
      api.clearBestTime.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await click('Remove the 5 km time');

      expect(gone).toBe(1);
    });

    it('says when the distance does not exist', async () => {
      api.clearBestTime.mockResolvedValue({ kind: 'not_found' });

      await click('Remove the 5 km time');

      expect(alerts()).toEqual(['That distance does not exist any more.']);
    });

    it('says something went wrong when the request fails', async () => {
      api.clearBestTime.mockRejectedValue(new Error('offline'));

      await click('Remove the 5 km time');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });
  });
});
