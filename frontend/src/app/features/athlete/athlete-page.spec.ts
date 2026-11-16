import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AthleteApi } from '../../core/athlete/athlete-api';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import {
  AthleteProfile,
  BestTimeDistance,
  BestTimeInput,
  BodyAndTraining,
  BodyChanges,
  ClearBestTimeResult,
  ClearThresholdResult,
  GetAthleteResult,
  SaveBodyResult,
  SetBestTimeResult,
  RideProfile,
  RunProfile,
  SetThresholdResult,
  SetTimezoneResult,
  SyncResult,
  Threshold,
  ThresholdSource,
  ThresholdValue,
  ZoneSet,
} from '../../core/athlete/athlete-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { AthletePage } from './athlete-page';

const HOUR = 60 * 60 * 1000;

function value(amount: number, source: ThresholdSource = 'manual', basis = ''): ThresholdValue {
  return { value: amount, source, basis, updated_at: '2026-11-13T10:00:00Z' };
}

function threshold(...candidates: ThresholdValue[]): Threshold {
  return { effective: candidates[0] ?? null, candidates };
}

const POWER: ZoneSet = {
  basis: 'ftp',
  zones: [
    { number: 1, name: 'Active recovery', lower: null, upper: 138, unit: 'W' },
    { number: 2, name: 'Endurance', lower: 138, upper: 188, unit: 'W' },
    { number: 7, name: 'Neuromuscular power', lower: 375, upper: null, unit: 'W' },
  ],
};
const RIDE_HR: ZoneSet = {
  basis: 'lthr',
  zones: [
    { number: 1, name: 'Recovery', lower: null, upper: 140, unit: 'bpm' },
    { number: 5, name: 'Super-threshold', lower: 165, upper: null, unit: 'bpm' },
  ],
};
const PACE: ZoneSet = {
  basis: 'threshold_pace',
  zones: [
    { number: 1, name: 'Recovery', lower: 387, upper: null, unit: 's/km' },
    { number: 5, name: 'Interval', lower: null, upper: 297, unit: 's/km' },
  ],
};

interface Parts {
  timezone?: string;
  body?: Partial<BodyAndTraining>;
  intervals?: AthleteProfile['intervals'];
  ride?: Partial<RideProfile['thresholds']>;
  run?: Partial<RunProfile['thresholds']>;
  zones?: {
    power?: ZoneSet | null;
    rideHr?: ZoneSet | null;
    pace?: ZoneSet | null;
    runHr?: ZoneSet | null;
  };
}

/** A profile: manual FTP, Intervals.icu LTHR, estimated maximum, manual pace, nothing else. */
function profile(parts: Parts = {}): AthleteProfile {
  const zones = parts.zones ?? {};
  return {
    best_times: { '5k': null, '10k': null, half_marathon: null, marathon: null },
    vdot: null,
    birth_year: null,
    sex: null,
    weight_kg: null,
    resting_hr: null,
    training_years: { running: null, cycling: null, swimming: null, strength: null },
    strength_experience: null,
    strength_equipment: [],
    ...parts.body,
    timezone: parts.timezone ?? 'Europe/Berlin',
    intervals: parts.intervals ?? { connected: false, synced_at: null },
    sports: {
      ride: {
        thresholds: {
          ftp: threshold(value(250)),
          lthr: threshold(value(165, 'intervals', 'Read from your Intervals.icu sport settings')),
          max_hr: threshold(
            value(190, 'estimated', 'Highest value reached in at least two activities'),
          ),
          ...parts.ride,
        },
        zones: {
          power: zones.power === undefined ? POWER : zones.power,
          heart_rate: zones.rideHr === undefined ? RIDE_HR : zones.rideHr,
        },
      },
      run: {
        thresholds: {
          threshold_pace: threshold(value(300)),
          lthr: threshold(),
          max_hr: threshold(),
          ...parts.run,
        },
        zones: {
          pace: zones.pace === undefined ? PACE : zones.pace,
          heart_rate: zones.runHr === undefined ? null : zones.runHr,
        },
      },
    },
  };
}

const ok = (parts?: Parts): { kind: 'ok'; profile: AthleteProfile } => ({
  kind: 'ok',
  profile: profile(parts),
});

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
  usage: { calls: 0, input_tokens: 0, output_tokens: 0, days: 30 },
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
    get: vi.fn<() => Promise<GetAthleteResult>>(),
    saveBody: vi.fn<(changes: BodyChanges) => Promise<SaveBodyResult>>(),
    setBestTime: vi.fn<(d: BestTimeDistance, i: BestTimeInput) => Promise<SetBestTimeResult>>(),
    clearBestTime: vi.fn<(d: BestTimeDistance) => Promise<ClearBestTimeResult>>(),
    setTimezone: vi.fn<(name: string) => Promise<SetTimezoneResult>>(),
    setThreshold:
      vi.fn<(sport: string, metric: string, amount: number) => Promise<SetThresholdResult>>(),
    clearThreshold: vi.fn<(sport: string, metric: string) => Promise<ClearThresholdResult>>(),
    syncFromIntervals: vi.fn<() => Promise<SyncResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('AthletePage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<AthletePage>;
  let page: HTMLElement;

  async function setup(first: GetAthleteResult = ok()) {
    api = createApiStub();
    api.get.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [AthletePage],
      providers: [
        provideRouter([]),
        { provide: AthleteApi, useValue: api },
        { provide: CoachApi, useValue: createCoachStub() },
      ],
    });
    fixture = TestBed.createComponent(AthletePage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const shown = (id: string) => query(page, `[data-testid="value-${id}"]`).textContent?.trim();
  const source = (id: string) => query(page, `[data-testid="source-${id}"]`).textContent?.trim();
  const others = (id: string) => page.querySelector(`[data-testid="others-${id}"]`)?.textContent;
  const field = (id: string) => query<HTMLInputElement>(page, `#edit-${id}`);
  const labelled = (label: string) =>
    page.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);

  function button(label: string): HTMLButtonElement {
    return required(labelled(label), `a button "${label}"`);
  }

  function buttonWithText(label: string): HTMLButtonElement {
    const match = Array.from(page.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(target: HTMLButtonElement): Promise<void> {
    target.click();
    await settle(fixture);
  }

  function type(input: HTMLInputElement, textValue: string): void {
    input.value = textValue;
    input.dispatchEvent(new Event('input'));
  }

  /** Opens the field of a row, types and presses its Save button. */
  async function edit(id: string, name: string, typed: string, submit = true): Promise<void> {
    await click(button(`Edit ${name}`));
    type(field(id), typed);
    if (submit) {
      await click(button(`Save ${name}`));
    }
  }

  const zoneRanges = (index: number) =>
    Array.from(page.querySelectorAll('table.zones')[index].querySelectorAll('tbody tr')).map(
      (row) => row.querySelectorAll('td')[2].textContent?.trim(),
    );

  describe('loading', () => {
    it('shows a loading note until the profile arrives', () => {
      api = createApiStub();
      api.get.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('table')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the profile cannot be loaded', async () => {
      api = createApiStub();
      api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok());
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your athlete profile could not be loaded.']);

      await click(buttonWithText('Try again'));

      expect(alerts()).toEqual([]);
      expect(shown('ride-ftp')).toBe('250 W');
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('table')).toBeNull();
    });
  });

  describe('what is shown', () => {
    beforeEach(() => setup());

    it('shows the values with their units', async () => {
      expect(shown('ride-ftp')).toBe('250 W');
      expect(shown('ride-lthr')).toBe('165 bpm');
      expect(shown('ride-max_hr')).toBe('190 bpm');
      expect(shown('run-threshold_pace')).toBe('5:00 /km');
    });

    it('shows "Not set" where there is no value', () => {
      expect(shown('run-lthr')).toBe('Not set');
      expect(shown('run-max_hr')).toBe('Not set');
      expect(page.querySelector('[data-testid="source-run-lthr"]')).toBeNull();
    });

    it('names the source of every value and says how an automatic one came about', () => {
      expect(source('ride-ftp')).toBe('You');
      expect(source('ride-lthr')).toBe('Intervals.icu');
      expect(source('ride-max_hr')).toBe('Estimated');
      expect(text()).toContain('Read from your Intervals.icu sport settings');
      expect(text()).toContain('Highest value reached in at least two activities');
    });

    it('names the sports and the thresholds', () => {
      expect(text()).toContain('Cycling');
      expect(text()).toContain('Running');
      for (const label of [
        'FTP',
        'Lactate threshold heart rate',
        'Maximum heart rate',
        'Threshold pace',
      ]) {
        expect(text()).toContain(label);
      }
    });

    it('offers "Use automatic value" only where the user typed a value', () => {
      expect(labelled('Use automatic value for FTP (Cycling)')).not.toBeNull();
      expect(labelled('Use automatic value for Threshold pace (Running)')).not.toBeNull();
      expect(labelled('Use automatic value for Lactate threshold heart rate (Cycling)')).toBeNull();
      expect(labelled('Use automatic value for Maximum heart rate (Cycling)')).toBeNull();
      expect(labelled('Use automatic value for Maximum heart rate (Running)')).toBeNull();
    });

    it('gives every row an Edit button that names the sport', () => {
      for (const name of [
        'FTP (Cycling)',
        'Lactate threshold heart rate (Cycling)',
        'Lactate threshold heart rate (Running)',
        'Maximum heart rate (Running)',
        'Threshold pace (Running)',
      ]) {
        expect(labelled(`Edit ${name}`)).not.toBeNull();
      }
    });
  });

  describe('values that do not count', () => {
    it('shows the typed value and lists the others as hints', async () => {
      await setup(
        ok({
          ride: {
            ftp: threshold(value(250), value(262, 'intervals', 'x'), value(241, 'estimated', 'y')),
          },
        }),
      );

      expect(shown('ride-ftp')).toBe('250 W');
      expect(source('ride-ftp')).toBe('You');
      expect(others('ride-ftp')).toContain('Also known: Intervals.icu 262 W, Estimated 241 W');
    });

    it('shows no hint when there is only one value', async () => {
      await setup();

      expect(others('ride-ftp')).toBeUndefined();
    });

    it('shows the value of a best time before Intervals.icu and the estimate', async () => {
      await setup(
        ok({
          run: {
            threshold_pace: threshold(
              value(255, 'best_time', 'VDOT 50.0 from your 5 km on 2026-10-03'),
              value(300, 'intervals', 'x'),
              value(310, 'estimated', 'y'),
            ),
          },
        }),
      );

      expect(shown('run-threshold_pace')).toBe('4:15 /km');
      expect(source('run-threshold_pace')).toBe('Best time');
      expect(text()).toContain('VDOT 50.0 from your 5 km on 2026-10-03');
      expect(others('run-threshold_pace')).toContain('Also known: Intervals.icu 5:00 /km');
    });

    it('shows the Intervals.icu value when nothing was typed in', async () => {
      await setup(
        ok({
          ride: { ftp: threshold(value(262, 'intervals', 'x'), value(241, 'estimated', 'y')) },
        }),
      );

      expect(shown('ride-ftp')).toBe('262 W');
      expect(source('ride-ftp')).toBe('Intervals.icu');
      expect(others('ride-ftp')).toContain('Estimated 241 W');
    });
  });

  describe('zones', () => {
    beforeEach(() => setup());

    it('shows the zones with their ranges', () => {
      expect(zoneRanges(0)).toEqual(['below 138 W', '138–187 W', '375 W and above']);
      expect(zoneRanges(1)).toEqual(['below 140 bpm', '165 bpm and above']);
      expect(zoneRanges(2)).toEqual(['6:27 /km or slower', 'faster than 4:57 /km']);
    });

    it('says what the zones are based on', () => {
      expect(text()).toContain('Based on your FTP.');
      expect(text()).toContain('Based on your lactate threshold heart rate.');
      expect(text()).toContain('Based on your threshold pace.');
    });

    it('says what to do where there are no zones', () => {
      expect(text()).toContain(
        'Set a lactate threshold or a maximum heart rate to see heart rate zones.',
      );
      expect(page.querySelectorAll('table.zones')).toHaveLength(3);
    });

    it('shows hints instead of tables when no zones exist at all', async () => {
      TestBed.resetTestingModule();
      await setup(ok({ zones: { power: null, rideHr: null, pace: null, runHr: null } }));

      expect(page.querySelectorAll('table.zones')).toHaveLength(0);
      expect(text()).toContain('Set your FTP to see power zones.');
      expect(text()).toContain('Set your threshold pace to see pace zones.');
    });

    it('names the zones by their sport', () => {
      expect(text()).toContain('Cycling: Power zones');
      expect(text()).toContain('Cycling: Heart rate zones');
      expect(text()).toContain('Running: Pace zones');
    });
  });

  describe('the time zone', () => {
    it('shows the saved time zone in the field', async () => {
      await setup(ok({ timezone: 'Asia/Tokyo' }));

      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('Asia/Tokyo');
    });

    it('suggests the zones the browser knows', async () => {
      vi.spyOn(Intl, 'supportedValuesOf').mockReturnValue(['Europe/Berlin', 'UTC']);
      await setup();

      const options = Array.from(page.querySelectorAll('#time-zones option')).map((o) =>
        o.getAttribute('value'),
      );
      expect(options).toEqual(['Europe/Berlin', 'UTC']);
    });

    it('works when the browser knows no list', async () => {
      vi.spyOn(Intl, 'supportedValuesOf').mockImplementation(() => {
        throw new RangeError('unsupported');
      });
      await setup();

      expect(page.querySelectorAll('#time-zones option')).toHaveLength(0);
      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('Europe/Berlin');
    });

    it("fills the field with the device's time zone without saving it", async () => {
      vi.spyOn(Intl, 'DateTimeFormat').mockReturnValue({
        resolvedOptions: () => ({ timeZone: 'America/Chicago' }),
      } as Intl.DateTimeFormat);
      await setup(ok({ timezone: '' }));

      await click(buttonWithText("Use this device's time zone"));

      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('America/Chicago');
      expect(api.setTimezone).not.toHaveBeenCalled();
    });

    it('leaves the field alone when the device does not say', async () => {
      vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(() => {
        throw new Error('no');
      });
      await setup(ok({ timezone: 'UTC' }));

      await click(buttonWithText("Use this device's time zone"));

      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('');
    });

    it('saves what was typed, without surrounding white space', async () => {
      await setup(ok({ timezone: '' }));
      api.setTimezone.mockResolvedValue(ok({ timezone: 'Europe/Paris' }));
      type(query<HTMLInputElement>(page, '#timezone'), '  Europe/Paris ');

      await click(buttonWithText('Save time zone'));

      expect(api.setTimezone).toHaveBeenCalledExactlyOnceWith('Europe/Paris');
      expect(text()).toContain('The time zone was saved.');
      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('Europe/Paris');
    });

    it('removes the time zone when the field is empty', async () => {
      await setup();
      api.setTimezone.mockResolvedValue(ok({ timezone: '' }));
      type(query<HTMLInputElement>(page, '#timezone'), '');

      await click(buttonWithText('Save time zone'));

      expect(api.setTimezone).toHaveBeenCalledExactlyOnceWith('');
      expect(text()).toContain('The time zone was removed.');
    });

    it('shows the message next to the field when the name is refused', async () => {
      await setup();
      api.setTimezone.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter a time zone from the IANA database, for example Europe/Berlin.'],
      });
      type(query<HTMLInputElement>(page, '#timezone'), 'Mars/Base');

      await click(buttonWithText('Save time zone'));

      expect(alerts()).toEqual([
        'Enter a time zone from the IANA database, for example Europe/Berlin.',
      ]);
      expect(query<HTMLInputElement>(page, '#timezone').getAttribute('aria-invalid')).toBe('true');
      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('Mars/Base');
    });

    it('clears an earlier message with the next try', async () => {
      await setup();
      api.setTimezone.mockResolvedValueOnce({ kind: 'invalid', errors: ['No.'] });
      api.setTimezone.mockResolvedValueOnce(ok({ timezone: 'UTC' }));
      type(query<HTMLInputElement>(page, '#timezone'), 'x');
      await click(buttonWithText('Save time zone'));

      type(query<HTMLInputElement>(page, '#timezone'), 'UTC');
      await click(buttonWithText('Save time zone'));

      expect(alerts()).toEqual([]);
    });

    it('shows the sign-in note when the session ended', async () => {
      await setup();
      api.setTimezone.mockResolvedValue({ kind: 'forbidden' });

      await click(buttonWithText('Save time zone'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when saving does not work', async () => {
      await setup();
      api.setTimezone.mockRejectedValue(new Error('offline'));

      await click(buttonWithText('Save time zone'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(query<HTMLInputElement>(page, '#timezone').value).toBe('Europe/Berlin');
    });

    it('does not send twice when the button is clicked twice in a row', async () => {
      await setup();
      const pending = deferred<SetTimezoneResult>();
      api.setTimezone.mockReturnValue(pending.promise);

      const save = buttonWithText('Save time zone');
      save.click();
      save.click();
      pending.resolve(ok());
      await settle(fixture);

      expect(api.setTimezone).toHaveBeenCalledTimes(1);
    });
  });

  describe('typing in a threshold', () => {
    beforeEach(() => setup());

    it('opens a field with the current value', async () => {
      await click(button('Edit FTP (Cycling)'));

      expect(field('ride-ftp').value).toBe('250');
      expect(page.querySelector('[data-testid="value-ride-ftp"]')).toBeNull();
    });

    it('opens the pace as minutes and seconds', async () => {
      await click(button('Edit Threshold pace (Running)'));

      expect(field('run-threshold_pace').value).toBe('5:00');
      expect(text()).toContain('Minutes and seconds per kilometre, for example 5:00.');
    });

    it('opens an empty field where nothing is set', async () => {
      await click(button('Edit Maximum heart rate (Running)'));

      expect(field('run-max_hr').value).toBe('');
    });

    it('lets a field be reached by its label', async () => {
      await click(button('Edit FTP (Cycling)'));

      const label = query(page, 'label[for="edit-ride-ftp"]');
      expect(label.textContent).toContain('New value for FTP (Cycling)');
    });

    it('opens only one field at a time', async () => {
      await click(button('Edit FTP (Cycling)'));

      await click(button('Edit Lactate threshold heart rate (Cycling)'));

      expect(page.querySelector('#edit-ride-ftp')).toBeNull();
      expect(page.querySelector('#edit-ride-lthr')).not.toBeNull();
    });

    it('does nothing when cancelled', async () => {
      await click(button('Edit FTP (Cycling)'));
      type(field('ride-ftp'), '999');

      await click(buttonWithText('Cancel'));

      expect(api.setThreshold).not.toHaveBeenCalled();
      expect(shown('ride-ftp')).toBe('250 W');
    });

    it('sends the value for cycling and shows the new profile', async () => {
      api.setThreshold.mockResolvedValue(
        ok({
          ride: { ftp: threshold(value(260)) },
          zones: { power: { ...POWER, zones: [{ ...POWER.zones[0], upper: 143 }] } },
        }),
      );

      await edit('ride-ftp', 'FTP (Cycling)', '260');

      expect(api.setThreshold).toHaveBeenCalledExactlyOnceWith('ride', 'ftp', 260);
      expect(shown('ride-ftp')).toBe('260 W');
      expect(page.querySelector('#edit-ride-ftp')).toBeNull();
      expect(text()).toContain('FTP was saved.');
      expect(zoneRanges(0)).toEqual(['below 143 W']);
    });

    it('sends running values to running and cycling values to cycling', async () => {
      api.setThreshold.mockResolvedValue(ok());

      await edit('run-lthr', 'Lactate threshold heart rate (Running)', '170');
      await edit('ride-lthr', 'Lactate threshold heart rate (Cycling)', '166');

      expect(api.setThreshold.mock.calls).toEqual([
        ['run', 'lthr', 170],
        ['ride', 'lthr', 166],
      ]);
    });

    it('sends a pace typed as minutes and seconds in seconds per kilometre', async () => {
      api.setThreshold.mockResolvedValue(ok());

      await edit('run-threshold_pace', 'Threshold pace (Running)', '4:59');

      expect(api.setThreshold).toHaveBeenCalledExactlyOnceWith('run', 'threshold_pace', 299);
    });

    it('accepts a comma as the decimal separator', async () => {
      api.setThreshold.mockResolvedValue(ok());

      await edit('ride-ftp', 'FTP (Cycling)', '250,5');

      expect(api.setThreshold).toHaveBeenCalledExactlyOnceWith('ride', 'ftp', 250.5);
    });

    it('saves with the Enter key', async () => {
      api.setThreshold.mockResolvedValue(ok());
      await click(button('Edit FTP (Cycling)'));
      type(field('ride-ftp'), '255');

      field('ride-ftp').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
      await settle(fixture);

      expect(api.setThreshold).toHaveBeenCalledExactlyOnceWith('ride', 'ftp', 255);
    });

    it.each([
      ['', 'Enter a value.'],
      ['abc', 'Enter a number, for example 250.'],
      ['25o', 'Enter a number, for example 250.'],
      ['5000', 'Enter a value between 30 and 2000 W.'],
      ['10', 'Enter a value between 30 and 2000 W.'],
    ])('refuses "%s" before sending anything', async (typed, message) => {
      await edit('ride-ftp', 'FTP (Cycling)', typed);

      expect(api.setThreshold).not.toHaveBeenCalled();
      expect(alerts()).toEqual([message]);
      expect(field('ride-ftp').getAttribute('aria-invalid')).toBe('true');
      expect(field('ride-ftp').getAttribute('aria-describedby')).toBe('error-ride-ftp');
    });

    it.each([
      ['300', 'Enter the pace as minutes and seconds per kilometre, for example 5:00.'],
      ['5.00', 'Enter the pace as minutes and seconds per kilometre, for example 5:00.'],
      ['5:60', 'Enter the pace as minutes and seconds per kilometre, for example 5:00.'],
      ['1:00', 'Enter a pace between 2:00 and 20:00 per km.'],
    ])('refuses the pace "%s" before sending anything', async (typed, message) => {
      await edit('run-threshold_pace', 'Threshold pace (Running)', typed);

      expect(api.setThreshold).not.toHaveBeenCalled();
      expect(alerts()).toEqual([message]);
    });

    it('lets the user correct a refused entry and try again', async () => {
      api.setThreshold.mockResolvedValue(ok());
      await edit('ride-ftp', 'FTP (Cycling)', 'abc');
      expect(alerts()).toHaveLength(1);

      type(field('ride-ftp'), '255');
      await click(button('Save FTP (Cycling)'));

      expect(api.setThreshold).toHaveBeenCalledExactlyOnceWith('ride', 'ftp', 255);
      expect(alerts()).toEqual([]);
    });

    it('shows the message of the server in the row and keeps the field open', async () => {
      api.setThreshold.mockResolvedValue({
        kind: 'invalid',
        errors: ['Cannot be above the maximum heart rate (190 bpm).'],
      });

      await edit('ride-lthr', 'Lactate threshold heart rate (Cycling)', '195');

      expect(alerts()).toEqual(['Cannot be above the maximum heart rate (190 bpm).']);
      expect(field('ride-lthr').value).toBe('195');
    });

    it('says when the threshold does not exist', async () => {
      api.setThreshold.mockResolvedValue({ kind: 'not_found' });

      await edit('ride-ftp', 'FTP (Cycling)', '250');

      expect(alerts()).toEqual(['FTP does not exist for this sport.']);
    });

    it('shows the sign-in note when the session ended', async () => {
      api.setThreshold.mockResolvedValue({ kind: 'forbidden' });

      await edit('ride-ftp', 'FTP (Cycling)', '250');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when saving does not work and keeps the field open', async () => {
      api.setThreshold.mockRejectedValue(new Error('offline'));

      await edit('ride-ftp', 'FTP (Cycling)', '260');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(field('ride-ftp').value).toBe('260');
    });

    it('does not send twice when Save is clicked twice in a row', async () => {
      const pending = deferred<SetThresholdResult>();
      api.setThreshold.mockReturnValue(pending.promise);
      await click(button('Edit FTP (Cycling)'));
      type(field('ride-ftp'), '260');

      const save = button('Save FTP (Cycling)');
      save.click();
      save.click();
      pending.resolve(ok());
      await settle(fixture);

      expect(api.setThreshold).toHaveBeenCalledTimes(1);
    });

    it('disables the other buttons while a value is being saved', async () => {
      const pending = deferred<SetThresholdResult>();
      api.setThreshold.mockReturnValue(pending.promise);
      await click(button('Edit FTP (Cycling)'));
      type(field('ride-ftp'), '260');
      button('Save FTP (Cycling)').click();
      fixture.detectChanges();

      expect(button('Save FTP (Cycling)').disabled).toBe(true);
      expect(buttonWithText('Save time zone').disabled).toBe(true);
      pending.resolve(ok());
      await settle(fixture);
      expect(buttonWithText('Save time zone').disabled).toBe(false);
    });
  });

  describe('going back to automatic', () => {
    beforeEach(() => setup());

    it('falls back to the next source and says so', async () => {
      api.clearThreshold.mockResolvedValue(
        ok({ ride: { ftp: threshold(value(262, 'intervals', 'x')) } }),
      );

      await click(button('Use automatic value for FTP (Cycling)'));

      expect(api.clearThreshold).toHaveBeenCalledExactlyOnceWith('ride', 'ftp');
      expect(shown('ride-ftp')).toBe('262 W');
      expect(source('ride-ftp')).toBe('Intervals.icu');
      expect(labelled('Use automatic value for FTP (Cycling)')).toBeNull();
      expect(text()).toContain('FTP is automatic again.');
    });

    it('shows "Not set" when nothing automatic exists', async () => {
      api.clearThreshold.mockResolvedValue(
        ok({ ride: { ftp: threshold() }, zones: { power: null } }),
      );

      await click(button('Use automatic value for FTP (Cycling)'));

      expect(shown('ride-ftp')).toBe('Not set');
      expect(text()).toContain('Set your FTP to see power zones.');
    });

    it('uses the right sport and metric for running', async () => {
      api.clearThreshold.mockResolvedValue(ok());

      await click(button('Use automatic value for Threshold pace (Running)'));

      expect(api.clearThreshold).toHaveBeenCalledExactlyOnceWith('run', 'threshold_pace');
    });

    it('does not offer it while that row is being edited', async () => {
      await click(button('Edit FTP (Cycling)'));

      expect(labelled('Use automatic value for FTP (Cycling)')).toBeNull();
      expect(labelled('Use automatic value for Threshold pace (Running)')).not.toBeNull();
    });

    it('leaves a field that is open in another row, with what was typed', async () => {
      api.clearThreshold.mockResolvedValue(ok());
      await click(button('Edit FTP (Cycling)'));
      type(field('ride-ftp'), '277');

      await click(button('Use automatic value for Threshold pace (Running)'));

      expect(field('ride-ftp').value).toBe('277');
    });

    it('says when the threshold does not exist', async () => {
      api.clearThreshold.mockResolvedValue({ kind: 'not_found' });

      await click(button('Use automatic value for FTP (Cycling)'));

      expect(alerts()).toEqual(['FTP does not exist for this sport.']);
    });

    it('shows the sign-in note when the session ended', async () => {
      api.clearThreshold.mockResolvedValue({ kind: 'forbidden' });

      await click(button('Use automatic value for FTP (Cycling)'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('says so when it does not work and keeps the value', async () => {
      api.clearThreshold.mockRejectedValue(new Error('offline'));

      await click(button('Use automatic value for FTP (Cycling)'));

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(shown('ride-ftp')).toBe('250 W');
    });

    it('does not send twice when clicked twice in a row', async () => {
      const pending = deferred<ClearThresholdResult>();
      api.clearThreshold.mockReturnValue(pending.promise);

      const target = button('Use automatic value for FTP (Cycling)');
      target.click();
      target.click();
      pending.resolve(ok());
      await settle(fixture);

      expect(api.clearThreshold).toHaveBeenCalledTimes(1);
    });
  });

  describe('Intervals.icu', () => {
    const connected = (hoursAgo: number | null) => ({
      connected: true,
      synced_at: hoursAgo === null ? null : new Date(Date.now() - hoursAgo * HOUR).toISOString(),
    });
    const updated = ok({ ride: { ftp: threshold(value(262, 'intervals', 'x')) } });

    it('reads nothing and points to the connections page when not connected', async () => {
      await setup();

      expect(api.syncFromIntervals).not.toHaveBeenCalled();
      expect(text()).toContain('Connect Intervals.icu on the Connections page');
      expect(page.querySelector('a[href="/settings/connections"]')).not.toBeNull();
      expect(() => buttonWithText('Update from Intervals.icu')).toThrow();
    });

    it('reads once on opening when it never has been read', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok({ intervals: connected(null) }));
      api.syncFromIntervals.mockResolvedValue(updated);
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
      expect(shown('ride-ftp')).toBe('262 W');
      expect(alerts()).toEqual([]);
      expect(text()).not.toContain('were updated from Intervals.icu');
    });

    it('reads on opening when the last read is older than a day', async () => {
      await setup(ok({ intervals: connected(25) }));

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
    });

    it('does not read on opening when the last read is fresh', async () => {
      await setup(ok({ intervals: connected(23) }));

      expect(api.syncFromIntervals).not.toHaveBeenCalled();
    });

    it('reads when the time of the last read cannot be understood', async () => {
      await setup(ok({ intervals: { connected: true, synced_at: 'yesterday' } }));

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
    });

    it('does not read on opening when not connected, however old the read is', async () => {
      await setup(
        ok({
          intervals: {
            connected: false,
            synced_at: new Date(Date.now() - 99 * HOUR).toISOString(),
          },
        }),
      );

      expect(api.syncFromIntervals).not.toHaveBeenCalled();
    });

    it('shows a note while it is reading', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok({ intervals: connected(null) }));
      const pending = deferred<SyncResult>();
      api.syncFromIntervals.mockReturnValue(pending.promise);
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(text()).toContain('Reading your thresholds from Intervals.icu…');
      expect(shown('ride-ftp')).toBe('250 W'); // the page works meanwhile
      expect(buttonWithText('Save time zone').disabled).toBe(true);
      pending.resolve(updated);
      await settle(fixture);
      expect(text()).not.toContain('Reading your thresholds');
    });

    describe.each([
      [
        'the key is refused',
        { kind: 'key_refused', message: 'The key is not accepted.' } as SyncResult,
        'The key is not accepted.',
      ],
      [
        'Intervals.icu is not available',
        { kind: 'unavailable', message: 'Try later.' } as SyncResult,
        'Try later.',
      ],
      [
        'the user reads too often',
        { kind: 'rate_limited' } as SyncResult,
        'Too many attempts. Please wait a minute and try again.',
      ],
      [
        'the connection is gone',
        { kind: 'not_connected' } as SyncResult,
        'There is no Intervals.icu connection any more.',
      ],
    ])('when %s', (_name, result, message) => {
      it('shows a note on opening and leaves the page usable', async () => {
        api = createApiStub();
        api.get.mockResolvedValue(ok({ intervals: connected(null) }));
        api.syncFromIntervals.mockResolvedValue(result);
        api.setThreshold.mockResolvedValue(ok());
        TestBed.configureTestingModule({
          imports: [AthletePage],
          providers: [
            provideRouter([]),
            { provide: AthleteApi, useValue: api },
            { provide: CoachApi, useValue: createCoachStub() },
          ],
        });
        fixture = TestBed.createComponent(AthletePage);
        page = fixture.nativeElement as HTMLElement;
        await settle(fixture);

        expect(alerts()).toEqual([message]);
        expect(shown('ride-ftp')).toBe('250 W');
        await edit('ride-ftp', 'FTP (Cycling)', '255');
        expect(api.setThreshold).toHaveBeenCalledTimes(1);
      });

      it('shows the same note after pressing the button', async () => {
        await setup(ok({ intervals: connected(1) }));
        api.syncFromIntervals.mockResolvedValue(result);

        await click(buttonWithText('Update from Intervals.icu'));

        expect(alerts()).toEqual([message]);
      });
    });

    it('shows a fixed note when the reading fails for another reason', async () => {
      await setup(ok({ intervals: connected(1) }));
      api.syncFromIntervals.mockRejectedValue(new Error('offline'));

      await click(buttonWithText('Update from Intervals.icu'));

      expect(alerts()).toEqual([
        'The thresholds could not be read from Intervals.icu. Please try again.',
      ]);
    });

    it('shows the sign-in note when the session ended', async () => {
      await setup(ok({ intervals: connected(1) }));
      api.syncFromIntervals.mockResolvedValue({ kind: 'forbidden' });

      await click(buttonWithText('Update from Intervals.icu'));

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('reads when the button is pressed and says so', async () => {
      await setup(ok({ intervals: connected(1) }));
      api.syncFromIntervals.mockResolvedValue(updated);

      await click(buttonWithText('Update from Intervals.icu'));

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
      expect(shown('ride-ftp')).toBe('262 W');
      expect(text()).toContain('The thresholds were updated from Intervals.icu.');
    });

    it('clears an earlier note when the button is pressed again', async () => {
      await setup(ok({ intervals: connected(1) }));
      api.syncFromIntervals.mockResolvedValueOnce({ kind: 'rate_limited' });
      api.syncFromIntervals.mockResolvedValueOnce(updated);
      await click(buttonWithText('Update from Intervals.icu'));
      expect(alerts()).toHaveLength(1);

      await click(buttonWithText('Update from Intervals.icu'));

      expect(alerts()).toEqual([]);
    });

    it('does not read twice when the button is clicked twice in a row', async () => {
      await setup(ok({ intervals: connected(1) }));
      const pending = deferred<SyncResult>();
      api.syncFromIntervals.mockReturnValue(pending.promise);

      const target = buttonWithText('Update from Intervals.icu');
      target.click();
      target.click();
      pending.resolve(updated);
      await settle(fixture);

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1);
    });

    it('does not read again on its own after the user changed something', async () => {
      await setup(ok({ intervals: connected(null) }));
      api.syncFromIntervals.mockResolvedValue(updated);
      api.setThreshold.mockResolvedValue(ok({ intervals: connected(null) }));

      await edit('ride-ftp', 'FTP (Cycling)', '255');

      expect(api.syncFromIntervals).toHaveBeenCalledTimes(1); // only the one on opening
    });

    it('shows when the thresholds were last read', async () => {
      await setup(ok({ intervals: connected(1) }));

      expect(query(page, '[data-testid="synced"]').textContent).toMatch(/Last read:\s+\w{3} \d/);
    });

    it('says "never" instead of failing when the time is no date', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok({ intervals: { connected: true, synced_at: 'yesterday' } }));
      api.syncFromIntervals.mockResolvedValue({ kind: 'not_connected' });
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(query(page, '[data-testid="synced"]').textContent).toContain('never');
      expect(shown('ride-ftp')).toBe('250 W');
    });

    it('says "never" when they were not read yet', async () => {
      api = createApiStub();
      api.get.mockResolvedValue(ok({ intervals: connected(null) }));
      api.syncFromIntervals.mockResolvedValue({ kind: 'not_connected' });
      TestBed.configureTestingModule({
        imports: [AthletePage],
        providers: [
          provideRouter([]),
          { provide: AthleteApi, useValue: api },
          { provide: CoachApi, useValue: createCoachStub() },
        ],
      });
      fixture = TestBed.createComponent(AthletePage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(query(page, '[data-testid="synced"]').textContent).toContain('never');
    });
  });
  describe('the body and training data', () => {
    beforeEach(() => setup(ok({ body: { weight_kg: 61.5 } })));

    it('are offered in a panel of their own, below the time zone and above Intervals.icu', () => {
      const panel = query(page, 'app-body-data-panel');

      expect(panel.textContent).toContain('About you');
      expect(
        query(page, '#timezone').compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(query<HTMLInputElement>(page, '#body-weight').value).toBe('61.5');
    });

    it('name the provider they go to', () => {
      expect(query(page, 'app-body-data-panel').textContent).toContain(
        'Where they go: Anthropic, model claude-sonnet-5-5.',
      );
    });

    it('are saved through the panel and the page says so', async () => {
      api.saveBody.mockResolvedValue(ok({ body: { weight_kg: 70 } }));
      typeInto(page, '#body-weight', '70');
      query<HTMLFormElement>(page, 'app-body-data-panel form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(api.saveBody).toHaveBeenCalledTimes(1);
      expect(query(page, 'app-body-data-panel [role="status"]').textContent).toContain('Saved.');
    });

    it('end the page when the session is gone', async () => {
      api.saveBody.mockResolvedValue({ kind: 'forbidden' });
      query<HTMLFormElement>(page, 'app-body-data-panel form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(text()).toContain('Your session has ended.');
      expect(page.querySelector('app-body-data-panel')).toBeNull();
    });
  });
  describe('the best times', () => {
    beforeEach(() => setup());

    it('are offered in a panel below the running thresholds', () => {
      const panel = query(page, 'app-best-times-panel');

      expect(panel.textContent).toContain('Best times');
      expect(
        query(page, '[data-testid="value-run-threshold_pace"]').compareDocumentPosition(panel) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(page.querySelectorAll('app-best-times-panel').length).toBe(1);
    });

    it('move the pace and the zones when one is saved', async () => {
      const moved = profile({
        run: {
          threshold_pace: threshold(
            value(255, 'best_time', 'VDOT 50.0 from your 5 km on 2026-10-03'),
          ),
        },
      });
      api.setBestTime.mockResolvedValue({
        kind: 'ok',
        profile: { ...moved, vdot: { value: 50, distance: '5k', date: '2026-10-03' } },
      });
      typeInto(page, '#best-time-5k', '19:57');
      typeInto(page, '#best-date-5k', '2026-10-03');
      await settle(fixture);

      query<HTMLFormElement>(page, '[data-testid="best-5k"] form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(shown('run-threshold_pace')).toBe('4:15 /km');
      expect(source('run-threshold_pace')).toBe('Best time');
      expect(query(page, '[data-testid="counting"]').textContent).toContain('Your VDOT: 50');
    });

    it('end the page when the session is gone', async () => {
      typeInto(page, '#best-time-5k', '19:57');
      typeInto(page, '#best-date-5k', '2026-10-03');
      api.setBestTime.mockResolvedValue({ kind: 'forbidden' });
      query<HTMLFormElement>(page, '[data-testid="best-5k"] form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await settle(fixture);

      expect(text()).toContain('Your session has ended.');
    });
  });
});
