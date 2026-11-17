import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AvailabilityApi } from '../../core/availability/availability-api';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import {
  Availability,
  AvailabilityChanges,
  AvailabilitySlot,
  GetAvailabilityResult,
  ListFixedSessionsResult,
  ListLimitationsResult,
  ListPeriodsResult,
  SaveAvailabilityResult,
} from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import { AvailabilityPage } from './availability-page';

const LEVEL_LIMITS: Availability['level_limits'] = {
  relaxed: {
    max_hard_days: 1,
    progression_warning_percent: 115,
    progression_error_percent: 130,
    easy_share_percent: 85,
  },
  normal: {
    max_hard_days: 2,
    progression_warning_percent: 120,
    progression_error_percent: 140,
    easy_share_percent: 80,
  },
  intensive: {
    max_hard_days: 3,
    progression_warning_percent: 130,
    progression_error_percent: 150,
    easy_share_percent: 75,
  },
};
const NO_OWN_LIMITS = {
  max_hard_days: null,
  progression_warning_percent: null,
  progression_error_percent: null,
  easy_share_percent: null,
};
const EVERY_PART: AvailabilitySlot[] = ['morning', 'afternoon', 'evening'];
const DAY_OPTIONS = {
  double_days: [true, true, true, true, true, true, true],
  time_windows: [
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
    EVERY_PART,
  ],
};
const NO_PREFERENCE = { role: null, sessions_min: null, sessions_max: null };
const NO_PREFERENCES = {
  sport_preferences: {
    running: NO_PREFERENCE,
    cycling: NO_PREFERENCE,
    swimming: NO_PREFERENCE,
    strength: NO_PREFERENCE,
  },
  strength_focus: null,
};
const NO_WISHES = {
  min_weekly_minutes: null,
  training_days: null,
  long_run_day: null,
  long_ride_day: null,
};
const SAVED: Availability = {
  weekdays: [60, 0, 90, 0, 0, 120, 180],
  ...NO_WISHES,
  ...NO_PREFERENCES,
  ...DAY_OPTIONS,
  weekly_budget_minutes: 300,
  typical_weekly_minutes: 360,
  sports: ['running', 'cycling'],
  stretching: true,
  limitations: 'No running on consecutive days',
  share_limitations_text: true,
  intensity_level: 'normal',
  ...NO_OWN_LIMITS,
  level_limits: LEVEL_LIMITS,
};
const NOTHING: Availability = {
  weekdays: [0, 0, 0, 0, 0, 0, 0],
  ...NO_WISHES,
  ...NO_PREFERENCES,
  ...DAY_OPTIONS,
  weekly_budget_minutes: null,
  typical_weekly_minutes: null,
  sports: ['running', 'cycling', 'swimming', 'strength'],
  stretching: false,
  limitations: '',
  share_limitations_text: false,
  intensity_level: 'normal',
  ...NO_OWN_LIMITS,
  level_limits: LEVEL_LIMITS,
};

const ok = (availability: Availability): GetAvailabilityResult => ({ kind: 'ok', availability });

const PROVIDER: AiProviderState = {
  configured: true,
  provider: 'anthropic',
  model: 'claude-sonnet-5-5',
  season_model: '',
  base_url: null,
  has_key: true,
  status: 'connected',
  last_checked_at: null,
  last_success_at: null,
  allowed_base_urls: [],
  usage: {
    calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    days: 30,
  },
};

function createCoachStub() {
  return {
    get: vi
      .fn<() => Promise<GetProviderResult>>()
      .mockResolvedValue({ kind: 'ok', state: PROVIDER }),
  };
}

function createApiStub() {
  return {
    get: vi.fn<() => Promise<GetAvailabilityResult>>(),
    save: vi.fn<(changes: AvailabilityChanges) => Promise<SaveAvailabilityResult>>(),
    // The periods have a panel of their own, tested in periods-panel.spec.ts.
    listPeriods: vi
      .fn<() => Promise<ListPeriodsResult>>()
      .mockResolvedValue({ kind: 'ok', periods: [] }),
    // The fixed appointments have a panel of their own, tested in fixed-sessions-panel.spec.ts.
    listFixedSessions: vi
      .fn<() => Promise<ListFixedSessionsResult>>()
      .mockResolvedValue({ kind: 'ok', sessions: [] }),
    // The limitations have a panel of their own, tested in limitations-panel.spec.ts.
    listLimitations: vi
      .fn<() => Promise<ListLimitationsResult>>()
      .mockResolvedValue({ kind: 'ok', limitations: [] }),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('AvailabilityPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let coach: ReturnType<typeof createCoachStub>;
  let fixture: ComponentFixture<AvailabilityPage>;
  let page: HTMLElement;

  async function setup(first: GetAvailabilityResult = ok(SAVED)) {
    api = createApiStub();
    coach = createCoachStub();
    api.get.mockResolvedValue(first);
    api.save.mockResolvedValue({ kind: 'ok', availability: SAVED });
    TestBed.configureTestingModule({
      imports: [AvailabilityPage],
      providers: [
        provideRouter([]),
        { provide: AvailabilityApi, useValue: api },
        { provide: CoachApi, useValue: coach },
      ],
    });
    fixture = TestBed.createComponent(AvailabilityPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLTextAreaElement>(page, selector).value;
  const days = () => [0, 1, 2, 3, 4, 5, 6].map((i) => value(`#day-${i}`));
  const total = () => page.querySelector('[data-testid="total"]')?.textContent?.trim() ?? null;
  const capNote = () => page.querySelector('[data-testid="cap-note"]')?.textContent?.trim() ?? null;

  async function type(selector: string, input: string): Promise<void> {
    typeInto(page, selector, input);
    await settle(fixture);
  }

  async function tick(selector: string): Promise<void> {
    query<HTMLInputElement>(page, selector).click();
    await settle(fixture);
  }

  const ticked = () =>
    ['running', 'cycling', 'swimming', 'strength'].filter(
      (sport) => query<HTMLInputElement>(page, `#sport-${sport}`).checked,
    );

  async function save(): Promise<void> {
    query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the answer arrives', () => {
      api = createApiStub();
      coach = createCoachStub();
      api.get.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when it cannot be loaded', async () => {
      api = createApiStub();
      coach = createCoachStub();
      api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(SAVED));
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your training time could not be loaded.']);

      query<HTMLButtonElement>(page, 'button.btn-primary').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(days()[0]).toBe('1:00');
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('form')).toBeNull();
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup());

    it('has a labelled field for every weekday, Monday first', () => {
      const labels = Array.from(page.querySelectorAll('.days label')).map((l) =>
        l.textContent?.trim(),
      );

      expect(labels).toEqual([
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday',
        'Sunday',
      ]);
      for (const [i, label] of Array.from(page.querySelectorAll('.days label')).entries()) {
        expect(label.getAttribute('for')).toBe(`day-${i}`);
      }
    });

    it('shows the saved values as hours and minutes', () => {
      expect(days()).toEqual(['1:00', '0:00', '1:30', '0:00', '0:00', '2:00', '3:00']);
      expect(value('#budget')).toBe('5:00');
      expect(value('#typical')).toBe('6:00');
      expect(value('#limitations')).toBe('No running on consecutive days');
    });

    it('adds the days up', () => {
      expect(total()).toBe('Together: 7:30 per week');
    });

    it('says what the weekly budget does when it is below the sum', () => {
      expect(capNote()).toBe(
        'Your weekly budget (5:00) is lower than the sum of the days, so a week offers at most 5:00.',
      );
    });
  });

  describe('a user who saved nothing', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('sees zeros, no budget and no limitations', () => {
      expect(days()).toEqual(Array(7).fill('0:00'));
      expect(value('#budget')).toBe('');
      expect(value('#typical')).toBe('');
      expect(value('#limitations')).toBe('');
      expect(total()).toBe('Together: 0:00 per week');
      expect(capNote()).toBeNull();
    });
  });

  describe('sports and stretching', () => {
    it('show what the server has: the ticked sports and the stretching flag', async () => {
      await setup(ok(SAVED));

      expect(ticked()).toEqual(['running', 'cycling']);
      expect(query<HTMLInputElement>(page, '#stretching').checked).toBe(true);
    });

    it('show all four sports ticked and no stretching for someone who chose nothing', async () => {
      await setup(ok(NOTHING));

      expect(ticked()).toEqual(['running', 'cycling', 'swimming', 'strength']);
      expect(query<HTMLInputElement>(page, '#stretching').checked).toBe(false);
    });

    it('label every box and group the sports', async () => {
      await setup(ok(NOTHING));

      const labels = ['running', 'cycling', 'swimming', 'strength'].map((sport) => {
        const label = query(page, `label[for="sport-${sport}"]`);
        return label.textContent?.trim();
      });
      expect(labels).toEqual(['Running', 'Cycling', 'Swimming', 'Strength / gym']);
      expect(query(page, 'fieldset legend').textContent?.trim()).toBe('Sports for your plan');
      expect(query(page, 'label[for="stretching"]').textContent?.trim()).toBe(
        'Add stretching to sessions',
      );
    });

    it('say that stretching is never a session of its own', async () => {
      await setup(ok(NOTHING));

      expect(query(page, '#stretching-hint').textContent).toContain('never a session of its own');
    });

    it('are sent as ticked, in the order of the server, whatever the order of ticking', async () => {
      await setup(ok(NOTHING));
      for (const sport of ['running', 'cycling', 'swimming', 'strength']) {
        await tick(`#sport-${sport}`); // all off
      }
      await tick('#sport-strength');
      await tick('#sport-running');
      await tick('#sport-swimming');
      await tick('#stretching');

      await save();

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(api.save.mock.calls[0][0].sports).toEqual(['running', 'swimming', 'strength']);
      expect(api.save.mock.calls[0][0].stretching).toBe(true);
    });

    it('switch stretching off again, and send it as it is', async () => {
      await setup(ok(SAVED));
      expect(query<HTMLInputElement>(page, '#stretching').checked).toBe(true);

      await tick('#stretching');
      expect(query<HTMLInputElement>(page, '#stretching').checked).toBe(false);
      await save();

      expect(api.save.mock.calls[0][0].stretching).toBe(false);
    });

    it('can be ticked off and on again', async () => {
      await setup(ok(NOTHING));

      await tick('#sport-swimming');
      expect(ticked()).toEqual(['running', 'cycling', 'strength']);

      await tick('#sport-swimming');
      expect(ticked()).toEqual(['running', 'cycling', 'swimming', 'strength']);
    });

    it('cannot all be ticked off: one sport is the least, and it says so next to them', async () => {
      await setup(ok(NOTHING));
      for (const sport of ['running', 'cycling', 'swimming', 'strength']) {
        await tick(`#sport-${sport}`);
      }

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Choose at least one sport.']);
      expect(query(page, '#sport-running').getAttribute('aria-invalid')).toBe('true');
    });

    it('clear the message as soon as a sport is ticked and saved', async () => {
      await setup(ok(NOTHING));
      for (const sport of ['running', 'cycling', 'swimming', 'strength']) {
        await tick(`#sport-${sport}`);
      }
      await save();

      await tick('#sport-cycling');
      await save();

      expect(alerts()).toEqual([]);
      expect(api.save.mock.calls[0][0].sports).toEqual(['cycling']);
    });

    it('show the server messages next to the sports', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Choose at least one of: running, cycling, swimming, strength.'],
        fields: { sports: ['Choose at least one of: running, cycling, swimming, strength.'] },
      });

      await save();

      expect(alerts()).toEqual(['Choose at least one of: running, cycling, swimming, strength.']);
      expect(query(page, '#sport-strength').getAttribute('aria-invalid')).toBe('true');
      expect(query(page, '#stretching').getAttribute('aria-invalid')).toBeNull();
    });

    it('show the server message about stretching next to it', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Send true or false.'],
        fields: { stretching: ['Send true or false.'] },
      });

      await save();

      expect(alerts()).toEqual(['Send true or false.']);
      expect(query(page, '#stretching').getAttribute('aria-invalid')).toBe('true');
      expect(query(page, '#sport-running').getAttribute('aria-invalid')).toBeNull();
    });

    it('show what the server has after saving', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, sports: ['swimming'], stretching: true },
      });
      await tick('#stretching');

      await save();

      expect(ticked()).toEqual(['swimming']);
      expect(query<HTMLInputElement>(page, '#stretching').checked).toBe(true);
    });
  });

  describe('parts of the day and two sessions', () => {
    const OPTIONS: Availability = {
      ...SAVED,
      double_days: [true, false, true, true, true, true, true],
      time_windows: [
        ['evening'],
        ['morning', 'evening'],
        EVERY_PART,
        EVERY_PART,
        EVERY_PART,
        EVERY_PART,
        EVERY_PART,
      ],
    };
    const window = (day: number, part: string) =>
      query<HTMLInputElement>(page, `#window-${day}-${part}`);
    const double = (day: number) => query<HTMLInputElement>(page, `#double-${day}`);

    it('shows every part of the day and two sessions for a user who chose nothing', async () => {
      await setup(ok(NOTHING));

      for (const day of [0, 1, 2, 3, 4, 5, 6]) {
        expect(double(day).checked).toBe(true);
        for (const part of ['morning', 'afternoon', 'evening']) {
          expect(window(day, part).checked).toBe(true);
        }
      }
    });

    it('shows the choice as saved', async () => {
      await setup(ok(OPTIONS));

      expect(double(1).checked).toBe(false);
      expect(double(0).checked).toBe(true);
      expect(['morning', 'afternoon', 'evening'].map((part) => window(0, part).checked)).toEqual([
        false,
        false,
        true,
      ]);
      expect(window(1, 'afternoon').checked).toBe(false);
      expect(window(1, 'morning').checked).toBe(true);
    });

    it('sends the choice with everything else, the parts in the order of the day', async () => {
      await setup(ok(NOTHING));

      await tick('#double-2');
      await tick('#window-0-morning');
      await tick('#window-0-afternoon');
      await tick('#window-4-afternoon');
      await tick('#window-4-afternoon');
      await save();

      const sent = api.save.mock.calls[0][0];
      expect(sent.double_days).toEqual([true, true, false, true, true, true, true]);
      expect(sent.time_windows?.[0]).toEqual(['evening']);
      expect(sent.time_windows?.[4]).toEqual(['morning', 'afternoon', 'evening']);
      expect(sent.time_windows?.[1]).toEqual(['morning', 'afternoon', 'evening']);
    });

    it('does not send a weekday without a part of the day and says so at the day', async () => {
      await setup(ok(NOTHING));

      await tick('#window-3-morning');
      await tick('#window-3-afternoon');
      await tick('#window-3-evening');
      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Thursday: Choose at least one part of the day.']);
      expect(window(3, 'morning').getAttribute('aria-invalid')).toBe('true');
      expect(window(2, 'morning').getAttribute('aria-invalid')).toBeNull();
    });

    it('takes the message away once the day has a part again', async () => {
      await setup(ok(NOTHING));
      for (const part of ['morning', 'afternoon', 'evening']) {
        await tick(`#window-3-${part}`);
      }
      await save();

      await tick('#window-3-evening');
      await save();

      expect(alerts()).toEqual([]);
      expect(api.save).toHaveBeenCalledOnce();
    });

    it('shows the server’s message about the time windows above the table', async () => {
      await setup(ok(NOTHING));
      const message = 'Enter seven lists of parts of the day, Monday first.';
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: [message],
        fields: { time_windows: [message] },
      });

      await save();

      expect(alerts()).toEqual([message]);
    });

    it('shows what the server saved', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({ kind: 'ok', availability: OPTIONS });

      await save();

      expect(double(1).checked).toBe(false);
      expect(window(0, 'morning').checked).toBe(false);
    });
  });

  describe('intensity', () => {
    const OWN: Availability = {
      ...SAVED,
      intensity_level: 'relaxed',
      max_hard_days: 2,
      progression_error_percent: 160,
    };
    const level = (name: string) => query<HTMLInputElement>(page, `#level-${name}`);

    it('shows the level and the own limits as saved', async () => {
      await setup(ok(OWN));

      expect(level('relaxed').checked).toBe(true);
      expect(value('#limit-max_hard_days')).toBe('2');
      expect(value('#limit-progression_warning_percent')).toBe('');
      expect(value('#limit-progression_error_percent')).toBe('160');
      expect(query<HTMLInputElement>(page, '#limit-easy_share_percent').placeholder).toBe('85');
    });

    it('sends the level and the own limits with everything else, empty ones as null', async () => {
      await setup();

      await tick('#level-intensive');
      await type('#limit-max_hard_days', '4');
      await type('#limit-easy_share_percent', ' 70 ');
      await save();

      expect(api.save.mock.calls[0][0]).toMatchObject({
        intensity_level: 'intensive',
        max_hard_days: 4,
        progression_warning_percent: null,
        progression_error_percent: null,
        easy_share_percent: 70,
        limitations: SAVED.limitations,
      });
    });

    it('takes back an own limit by emptying its field', async () => {
      await setup(ok(OWN));

      await type('#limit-max_hard_days', '');
      await save();

      expect(api.save.mock.calls[0][0]).toMatchObject({
        intensity_level: 'relaxed',
        max_hard_days: null,
        progression_error_percent: 160,
      });
    });

    it('does not send an own limit out of range and says so at the field', async () => {
      await setup();

      await type('#limit-max_hard_days', '7');
      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Enter a whole number of days between 0 and 4.']);
      expect(
        query<HTMLInputElement>(page, '#limit-max_hard_days').getAttribute('aria-invalid'),
      ).toBe('true');
    });

    it('checks the warning against the error of the level chosen now', async () => {
      await setup();
      await type('#limit-progression_warning_percent', '135');

      await tick('#level-relaxed');
      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual([
        'The warning limit (135 %) must be below the error limit (130 %).',
      ]);
    });

    it('shows the server’s messages at the fields of the intensity', async () => {
      await setup();
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['The warning limit (150 %) must be below the error limit (140 %).'],
        fields: {
          progression_warning_percent: [
            'The warning limit (150 %) must be below the error limit (140 %).',
          ],
        },
      });

      await save();

      expect(query(page, '#limit-progression_warning_percent-error').textContent?.trim()).toBe(
        'The warning limit (150 %) must be below the error limit (140 %).',
      );
      // shown at its field only, not once more at the top
      expect(alerts()).toEqual([
        'The warning limit (150 %) must be below the error limit (140 %).',
      ]);
    });

    it('shows what the server saved', async () => {
      await setup();
      api.save.mockResolvedValue({ kind: 'ok', availability: OWN });

      await save();

      expect(level('relaxed').checked).toBe(true);
      expect(value('#limit-progression_error_percent')).toBe('160');
    });
  });

  describe('the sum while typing', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('follows every change', async () => {
      await type('#day-0', '90');
      expect(total()).toBe('Together: 1:30 per week');

      await type('#day-6', '1:00');
      expect(total()).toBe('Together: 2:30 per week');

      await type('#day-0', '');
      expect(total()).toBe('Together: 1:00 per week');
    });

    it('is not shown while a field is not a usable time', async () => {
      await type('#day-0', '60');
      await type('#day-1', 'abc');

      expect(total()).toBeNull();
    });

    it('comes back when the field is right again', async () => {
      await type('#day-1', 'abc');
      await type('#day-1', '30');

      expect(total()).toBe('Together: 0:30 per week');
    });

    it('says nothing about the budget when it is not below the sum', async () => {
      await type('#day-0', '60');
      await type('#budget', '1:00');
      expect(capNote()).toBeNull();

      await type('#budget', '2:00');
      expect(capNote()).toBeNull();
    });

    it('says it as soon as the budget is below the sum', async () => {
      await type('#day-0', '60');
      await type('#budget', '0:30');

      expect(capNote()).toContain('(0:30)');
    });

    it('does not compare the typical week with the days or the budget', async () => {
      await type('#day-0', '60');

      await type('#typical', '40:00');
      expect(capNote()).toBeNull();

      await type('#budget', '0:30');
      expect(capNote()).toContain('weekly budget');
      expect(capNote()).not.toContain('typical');
    });

    it('says nothing for an empty or unusable budget', async () => {
      await type('#day-0', '60');
      await type('#budget', 'abc');
      expect(capNote()).toBeNull();

      await type('#budget', '');
      expect(capNote()).toBeNull();
    });

    it('says nothing while a day is unusable', async () => {
      await type('#budget', '0:30');
      await type('#day-0', '60');
      await type('#day-1', 'abc');

      expect(capNote()).toBeNull();
    });
  });

  describe('saving', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('sends everything together, minutes as numbers', async () => {
      await type('#day-0', '90');
      await type('#day-2', '1:30');
      await type('#day-6', '180');
      await type('#budget', '5:00');
      await type('#typical', '8:30');
      await type('#limitations', 'Knee');

      await save();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        weekdays: [90, 0, 90, 0, 0, 0, 180],
        ...DAY_OPTIONS,
        weekly_budget_minutes: 300,
        ...NO_WISHES,
        ...NO_PREFERENCES,
        typical_weekly_minutes: 510,
        sports: ['running', 'cycling', 'swimming', 'strength'],
        stretching: false,
        limitations: 'Knee',
        share_limitations_text: false,
        intensity_level: 'normal',
        ...NO_OWN_LIMITS,
      });
    });

    it('sends no budget as null and empty days as zero', async () => {
      await type('#day-0', '');

      await save();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        weekdays: [0, 0, 0, 0, 0, 0, 0],
        ...DAY_OPTIONS,
        weekly_budget_minutes: null,
        ...NO_WISHES,
        ...NO_PREFERENCES,
        typical_weekly_minutes: null,
        sports: ['running', 'cycling', 'swimming', 'strength'],
        stretching: false,
        limitations: '',
        share_limitations_text: false,
        intensity_level: 'normal',
        ...NO_OWN_LIMITS,
      });
    });

    it('sends a typical week of zero as zero and an empty one as null', async () => {
      await type('#typical', '0');
      await save();
      await type('#typical', '');
      await save();

      expect(api.save.mock.calls.map(([sent]) => sent.typical_weekly_minutes)).toEqual([0, null]);
    });

    it('sends a budget of zero as zero', async () => {
      await type('#budget', '0');

      await save();

      expect(api.save.mock.calls[0][0].weekly_budget_minutes).toBe(0);
    });

    it('takes the limits themselves', async () => {
      for (let i = 0; i < 7; i++) {
        await type(`#day-${i}`, '24:00');
      }
      await type('#budget', '168:00');
      await type('#typical', '168:00');
      await type('#limitations', 'x'.repeat(1000));

      await save();

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(api.save.mock.calls[0][0].weekdays).toEqual(Array(7).fill(1440));
      expect(api.save.mock.calls[0][0].weekly_budget_minutes).toBe(10080);
      expect(api.save.mock.calls[0][0].typical_weekly_minutes).toBe(10080);
    });

    it('shows what the server has now and says it was saved', async () => {
      api.save.mockResolvedValue({ kind: 'ok', availability: SAVED });
      await type('#day-0', '60');

      await save();

      expect(days()).toEqual(['1:00', '0:00', '1:30', '0:00', '0:00', '2:00', '3:00']);
      expect(value('#budget')).toBe('5:00');
      expect(text()).toContain('Your training time was saved.');
    });

    it('writes what was typed in the form of the answer', async () => {
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, weekdays: [90, 0, 0, 0, 0, 0, 0] },
      });
      await type('#day-0', '90');

      await save();

      expect(value('#day-0')).toBe('1:30');
    });

    it('clears the note with the next try', async () => {
      await save();
      expect(text()).toContain('Your training time was saved.');

      await type('#day-0', 'abc');
      await save();

      expect(text()).not.toContain('Your training time was saved.');
    });

    it('does not let the browser submit the page', async () => {
      const event = new Event('submit', { cancelable: true });
      query<HTMLFormElement>(page, 'form').dispatchEvent(event);
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
    });

    it('sends only once when submitted twice in a row, and shows that it is saving', async () => {
      const pending = deferred<SaveAvailabilityResult>();
      api.save.mockReturnValue(pending.promise);

      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      query<HTMLFormElement>(page, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
      await fixture.whenStable();
      fixture.detectChanges();
      const button = query<HTMLButtonElement>(page, 'button[type="submit"]');
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Saving');
      pending.resolve({ kind: 'ok', availability: NOTHING });
      await settle(fixture);

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(button.disabled).toBe(false);
    });
  });

  describe('input that cannot be used', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it.each(['abc', '1:5', '1:60', '-5', '1,5', '1441', '24:01'])(
      'refuses "%s" as a day, names the field and sends nothing',
      async (input) => {
        await type('#day-2', input);

        await save();

        expect(api.save).not.toHaveBeenCalled();
        expect(alerts()).toHaveLength(1);
        expect(query(page, '#day-2').getAttribute('aria-invalid')).toBe('true');
        expect(query(page, '#day-2').getAttribute('aria-describedby')).toBe('day-2-error');
        expect(query(page, '#day-2-error').textContent).toBeTruthy();
        expect(query(page, '#day-1').getAttribute('aria-invalid')).toBeNull();
      },
    );

    it('says what is expected and what the limit is', async () => {
      await type('#day-0', 'abc');
      await type('#day-1', '25:00');

      await save();

      expect(query(page, '#day-0-error').textContent?.trim()).toBe(
        'Enter minutes (90) or hours and minutes (1:30).',
      );
      expect(query(page, '#day-1-error').textContent?.trim()).toBe(
        'Enter at most 24:00 (1440 minutes).',
      );
    });

    it.each(['abc', '168:01', '10081'])('refuses "%s" as a budget', async (input) => {
      await type('#budget', input);

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toHaveLength(1);
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBe('true');
    });

    it.each(['abc', '168:01', '10081'])('refuses "%s" as a typical week', async (input) => {
      await type('#typical', input);

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toHaveLength(1);
      expect(query(page, '#typical').getAttribute('aria-invalid')).toBe('true');
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBeNull();
    });

    it('refuses limitations of more than 1000 characters', async () => {
      await type('#limitations', 'x'.repeat(1001));

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['Use at most 1000 characters.']);
      expect(query(page, '#limitations').getAttribute('aria-invalid')).toBe('true');
    });

    it('names every problem at once', async () => {
      await type('#day-0', 'abc');
      await type('#day-6', 'xyz');
      await type('#budget', 'abc');
      await type('#limitations', 'x'.repeat(1001));

      await save();

      expect(alerts()).toHaveLength(4);
      expect(api.save).not.toHaveBeenCalled();
    });

    it('clears the messages once everything is right', async () => {
      await type('#day-0', 'abc');
      await type('#budget', 'abc');
      await save();
      expect(alerts()).toHaveLength(2);

      await type('#day-0', '60');
      await type('#budget', '');
      await save();

      expect(alerts()).toEqual([]);
      expect(api.save).toHaveBeenCalledTimes(1);
    });
  });

  describe('the page as cards', () => {
    it('says what the days add up to under the title', async () => {
      await setup();

      expect(query(page, '[data-testid=subtitle]').textContent).toMatch(/ per week$/);
    });

    it('has the sections as cards of one form with one save button', async () => {
      await setup();

      expect(page.querySelectorAll('form > .card').length).toBeGreaterThanOrEqual(7);
      expect(page.querySelectorAll('form > .actions button[type="submit"]')).toHaveLength(1);
    });
  });

  describe('what the server says', () => {
    beforeEach(() => setup(ok(NOTHING)));

    it('shows a message about the weekdays above them', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter seven numbers of minutes, Monday first.'],
        fields: { weekdays: ['Enter seven numbers of minutes, Monday first.'] },
      });

      await save();

      expect(alerts()).toEqual(['Enter seven numbers of minutes, Monday first.']);
      expect(query(page, 'form > .card:first-child > .field-error').textContent).toContain(
        'seven numbers',
      );
    });

    it('shows a message about the budget next to it', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter whole minutes between 0 and 10080.'],
        fields: { weekly_budget_minutes: ['Enter whole minutes between 0 and 10080.'] },
      });

      await save();

      expect(alerts()).toEqual(['Enter whole minutes between 0 and 10080.']);
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message about the typical week next to it', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter whole minutes between 0 and 10080.'],
        fields: { typical_weekly_minutes: ['Enter whole minutes between 0 and 10080.'] },
      });

      await save();

      expect(alerts()).toEqual(['Enter whole minutes between 0 and 10080.']);
      expect(query(page, '#typical').getAttribute('aria-invalid')).toBe('true');
      expect(query(page, '#budget').getAttribute('aria-invalid')).toBeNull();
    });

    it('shows a message about the limitations next to them', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Not a valid string.'],
        fields: { limitations: ['Not a valid string.'] },
      });

      await save();

      expect(alerts()).toEqual(['Not a valid string.']);
      expect(query(page, '#limitations').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message about anything else at the top, once', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Something odd.'],
        fields: { non_field_errors: ['Something odd.'] },
      });

      await save();

      expect(alerts()).toEqual(['Something odd.']);
      expect(query(page, 'form').previousElementSibling?.textContent).toContain('Something odd.');
    });

    it('shows a refusal without fields as it is', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });

      await save();

      expect(alerts()).toEqual(['The input was not accepted.']);
    });

    it('joins several messages for one field', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['First.', 'Second.'],
        fields: { weekly_budget_minutes: ['First.', 'Second.'] },
      });

      await save();

      expect(alerts()).toEqual(['First. Second.']);
    });

    it('clears an earlier message at the top once a save works', async () => {
      api.save.mockResolvedValueOnce({
        kind: 'invalid',
        errors: ['Something odd.'],
        fields: { non_field_errors: ['Something odd.'] },
      });
      await save();
      expect(alerts()).toEqual(['Something odd.']);

      await save();

      expect(alerts()).toEqual([]);
    });

    it('keeps what the user typed', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['No.'],
        fields: { weekdays: ['No.'] },
      });
      await type('#day-3', '45');

      await save();

      expect(value('#day-3')).toBe('45');
    });

    it('says that the session has ended', async () => {
      api.save.mockResolvedValue({ kind: 'forbidden' });

      await save();

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when saving does not work', async () => {
      api.save.mockRejectedValue(new Error('offline'));

      await save();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(page.querySelector('form')).not.toBeNull();
    });
  });

  describe('sport preferences and the strength focus', () => {
    const select = (id: string) => query<HTMLSelectElement>(page, `#${id}`);

    async function choose(id: string, value: string): Promise<void> {
      const box = select(id);
      box.value = value;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
    }

    it('show what is saved', async () => {
      await setup(
        ok({
          ...SAVED,
          sport_preferences: {
            ...NO_PREFERENCES.sport_preferences,
            running: { role: 'goal', sessions_min: 3, sessions_max: 5 },
          },
          strength_focus: 'legs',
        }),
      );

      expect(select('role-running').value).toBe('goal');
      expect(value('#min-running')).toBe('3');
      expect(value('#max-running')).toBe('5');
      expect(select('strength-focus').value).toBe('legs');
      expect(select('role-cycling').value).toBe('');
    });

    it('are sent as a whole, nothing said as null', async () => {
      await setup(ok(NOTHING));

      await choose('role-running', 'goal');
      await type('#min-running', '3');
      await choose('strength-focus', 'full_body');
      await save();

      const sent = api.save.mock.calls[0][0];
      expect(sent.sport_preferences).toEqual({
        ...NO_PREFERENCES.sport_preferences,
        running: { role: 'goal', sessions_min: 3, sessions_max: null },
      });
      expect(sent.strength_focus).toBe('full_body');
    });

    it('do not send counts that cannot be used and say so at the sport', async () => {
      await setup(ok(NOTHING));
      await type('#min-cycling', '5');
      await type('#max-cycling', '2');

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual([
        'Cycling: Enter whole numbers of sessions between 0 and 14, the least not above the most.',
      ]);
      expect(query(page, '#min-cycling').getAttribute('aria-invalid')).toBe('true');
    });

    it('show the server’s message about them as a whole', async () => {
      await setup(ok(NOTHING));
      const message = 'Send an object with running, cycling, swimming, strength.';
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: [message],
        fields: { sport_preferences: [message] },
      });

      await save();

      expect(alerts()).toEqual([message]);
    });

    it('show what the server saved', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, strength_focus: 'core' },
      });

      await save();

      expect(select('strength-focus').value).toBe('core');
    });
  });

  describe('the wishes for a week', () => {
    const select = (id: string) => query<HTMLSelectElement>(page, `#${id}`);

    async function choose(id: string, value: string): Promise<void> {
      const box = select(id);
      box.value = value;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
    }

    it('are empty for a user who chose nothing and shown as saved otherwise', async () => {
      await setup(
        ok({
          ...SAVED,
          min_weekly_minutes: 240,
          training_days: 4,
          long_run_day: 5,
          long_ride_day: 6,
        }),
      );

      expect(select('wish-training-days').value).toBe('4');
      expect(value('#wish-minimum')).toBe('4:00');
      expect(select('wish-long-run').value).toBe('5');
      expect(select('wish-long-ride').value).toBe('6');
    });

    it('are sent with everything else, empty ones as null', async () => {
      await setup(ok(NOTHING));

      await choose('wish-training-days', '3');
      await choose('wish-long-ride', '6');
      await type('#wish-minimum', '4:30');
      await save();

      expect(api.save.mock.calls[0][0]).toMatchObject({
        training_days: 3,
        min_weekly_minutes: 270,
        long_run_day: null,
        long_ride_day: 6,
      });
    });

    it('send no wish for a user who chose none', async () => {
      await setup(ok(NOTHING));

      await save();

      expect(api.save.mock.calls[0][0]).toMatchObject({
        training_days: null,
        min_weekly_minutes: null,
        long_run_day: null,
        long_ride_day: null,
      });
    });

    it('do not send a minimum above the budget and say so at the minimum', async () => {
      await setup(ok(NOTHING));
      await type('#budget', '4:00');
      await type('#wish-minimum', '5:00');

      await save();

      expect(api.save).not.toHaveBeenCalled();
      expect(alerts()).toEqual(['The minimum cannot be above your weekly budget.']);
      expect(select('wish-training-days').getAttribute('aria-invalid')).toBeNull();
      expect(query(page, '#wish-minimum').getAttribute('aria-invalid')).toBe('true');
    });

    it('show the server’s message at the field', async () => {
      await setup(ok(NOTHING));
      const message = 'The weekly budget cannot be below your minimum.';
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: [message],
        fields: { weekly_budget_minutes: [message] },
      });

      await save();

      expect(alerts()).toEqual([message]);
    });

    it('show what the server saved', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, training_days: 5, min_weekly_minutes: 120 },
      });

      await save();

      expect(select('wish-training-days').value).toBe('5');
      expect(value('#wish-minimum')).toBe('2:00');
    });
  });

  describe('sending the free text to the coach', () => {
    const box = () => query<HTMLInputElement>(page, '#share-limitations');

    it('is off for a user who chose nothing', async () => {
      await setup(ok(NOTHING));

      expect(box().checked).toBe(false);
    });

    it('shows the choice as saved', async () => {
      await setup(ok(SAVED));

      expect(box().checked).toBe(true);
    });

    it('says what is sent, how much and where, and that it is off unless switched on', async () => {
      await setup(ok(NOTHING));

      const hint = query(page, '#share-limitations-hint').textContent ?? '';
      const flat = hint.split(/\s+/).join(' ');

      expect(flat).toContain('Off unless you switch it on');
      expect(flat).toContain('the first 150 characters go to Anthropic, model claude-sonnet-5-5');
      expect(flat).toContain('never as instructions');
      expect(flat).toContain('sent as a body part and sports either way');
      expect(query(page, 'label[for="share-limitations"]').textContent?.trim()).toBe(
        'Send this text to my AI coach',
      );
    });

    it('sends the choice with everything else', async () => {
      await setup(ok(NOTHING));

      await tick('#share-limitations');
      await save();

      expect(api.save.mock.calls[0][0].share_limitations_text).toBe(true);
    });

    it('sends off when it was ticked and unticked again', async () => {
      await setup(ok(SAVED));

      await tick('#share-limitations');
      await save();

      expect(api.save.mock.calls[0][0].share_limitations_text).toBe(false);
    });

    it('does not switch itself on when the text is written', async () => {
      await setup(ok(NOTHING));

      await type('#limitations', 'Right knee');
      await save();

      expect(api.save.mock.calls[0][0].share_limitations_text).toBe(false);
    });

    it('shows the server’s message next to the box', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Send true or false.'],
        fields: { share_limitations_text: ['Send true or false.'] },
      });

      await save();

      expect(alerts()).toEqual(['Send true or false.']);
      expect(box().getAttribute('aria-invalid')).toBe('true');
    });

    it('shows what the server saved', async () => {
      await setup(ok(NOTHING));
      api.save.mockResolvedValue({
        kind: 'ok',
        availability: { ...NOTHING, share_limitations_text: true },
      });

      await save();

      expect(box().checked).toBe(true);
    });
  });

  describe('the fixed appointments', () => {
    it('are shown below the form and above the limitations', async () => {
      await setup();

      const panel = query(page, 'app-fixed-sessions-panel');
      expect(panel.textContent).toContain('Fixed appointments');
      expect(
        query(page, 'form').compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        panel.compareDocumentPosition(query(page, 'app-limitations-panel')) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });
  });

  describe('the limitations', () => {
    it('are shown below the form and above the periods', async () => {
      await setup();

      const panel = query(page, 'app-limitations-panel');
      expect(panel.textContent).toContain('Injuries and limitations');
      expect(
        query(page, 'form').compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        panel.compareDocumentPosition(query(page, 'app-periods-panel')) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(api.listLimitations).toHaveBeenCalledTimes(1);
    });

    it('name the provider the entries go to', async () => {
      await setup();

      expect(query(page, 'app-limitations-panel').textContent).toContain(
        'Where they go: Anthropic, model claude-sonnet-5-5.',
      );
      expect(coach.get).toHaveBeenCalledTimes(1);
    });

    it('say that nothing is sent when no provider is set up', async () => {
      await setup();
      coach.get.mockResolvedValue({
        kind: 'ok',
        state: { ...PROVIDER, configured: false, provider: null, model: '', has_key: false },
      });
      api.get.mockResolvedValue(ok(SAVED));
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(query(page, 'app-limitations-panel').textContent).toContain(
        'no AI provider is set up yet, so nothing is sent',
      );
    });

    it('still work when the provider cannot be read', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok(SAVED));
      coach = createCoachStub();
      coach.get.mockRejectedValue(new Error('offline'));
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(query(page, 'app-limitations-panel').textContent).toContain(
        'Where they go: your AI provider.',
      );
      expect(alerts()).toEqual([]);
    });

    it('end the session of the page when they find it gone', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok(SAVED));
      api.listLimitations.mockResolvedValue({ kind: 'forbidden' });
      coach = createCoachStub();
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('app-limitations-panel')).toBeNull();
    });
  });

  describe('the periods', () => {
    it('are shown below the form', async () => {
      await setup();

      const panel = query(page, 'app-periods-panel');
      expect(panel.textContent).toContain('Not available');
      expect(
        query(page, 'form').compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(api.listPeriods).toHaveBeenCalledTimes(1);
    });

    it('end the session of the page when they find it gone', async () => {
      api = createApiStub();
      coach = createCoachStub();
      api.get.mockResolvedValue(ok(SAVED));
      api.listPeriods.mockResolvedValue({ kind: 'forbidden' });
      TestBed.configureTestingModule({
        imports: [AvailabilityPage],
        providers: [
          provideRouter([]),
          { provide: AvailabilityApi, useValue: api },
          { provide: CoachApi, useValue: coach },
        ],
      });
      fixture = TestBed.createComponent(AvailabilityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('form')).toBeNull();
      expect(page.querySelector('app-periods-panel')).toBeNull();
    });
  });

  describe('free text', () => {
    it('shows the limitations as text and never as markup', async () => {
      await setup(ok({ ...NOTHING, limitations: '<img src=x onerror=alert(1)><b>bold</b>' }));

      expect(value('#limitations')).toBe('<img src=x onerror=alert(1)><b>bold</b>');
      expect(page.querySelector('img')).toBeNull();
      expect(page.querySelector('b')).toBeNull();
    });
  });
});
