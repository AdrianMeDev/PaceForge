import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AthleteApi } from '../../core/athlete/athlete-api';
import { AthleteProfile, BodyChanges, SaveBodyResult } from '../../core/athlete/athlete-models';
import { query, settle, typeInto } from '../../testing/dom';
import { BodyDataPanel } from './body-data-panel';

const NOTHING = {
  birth_year: null,
  sex: null,
  weight_kg: null,
  resting_hr: null,
  training_years: { running: null, cycling: null, swimming: null, strength: null },
  strength_experience: null,
  strength_equipment: [],
};

function profile(body: Partial<AthleteProfile> = {}): AthleteProfile {
  return {
    ...NOTHING,
    best_times: { '5k': null, '10k': null, half_marathon: null, marathon: null },
    vdot: null,
    ...body,
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
  } as AthleteProfile;
}

const FULL = profile({
  birth_year: 1985,
  sex: 'female',
  weight_kg: 61.5,
  resting_hr: 48,
  training_years: { running: 12, cycling: 3, swimming: null, strength: 0 },
  strength_experience: 'beginner',
  strength_equipment: ['gym', 'dumbbells'],
});

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('BodyDataPanel', () => {
  let api: { saveBody: ReturnType<typeof vi.fn<(c: BodyChanges) => Promise<SaveBodyResult>>> };
  let fixture: ComponentFixture<BodyDataPanel>;
  let panel: HTMLElement;

  async function setup(start: AthleteProfile = profile()) {
    api = { saveBody: vi.fn() };
    api.saveBody.mockResolvedValue({ kind: 'ok', profile: start });
    TestBed.configureTestingModule({
      imports: [BodyDataPanel],
      providers: [{ provide: AthleteApi, useValue: api }],
    });
    fixture = TestBed.createComponent(BodyDataPanel);
    fixture.componentRef.setInput('profile', start);
    fixture.componentRef.setInput('provider', 'Anthropic, model claude-sonnet-5-5');
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const notice = () => panel.querySelector('[role="status"]')?.textContent?.trim();
  const value = (id: string) => query<HTMLInputElement | HTMLSelectElement>(panel, `#${id}`).value;

  async function type(id: string, text: string): Promise<void> {
    typeInto(panel, `#${id}`, text);
    await settle(fixture);
  }

  async function choose(id: string, option: string): Promise<void> {
    const select = query<HTMLSelectElement>(panel, `#${id}`);
    select.value = option;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(panel, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  describe('what is shown', () => {
    it('says what the coach is told and where it goes', async () => {
      await setup();

      const text = panel.textContent ?? '';
      expect(text).toContain('which is not sent');
      expect(text).toContain('as numbers and fixed words and without any text of yours');
      expect(text).toContain('Where they go: Anthropic, model claude-sonnet-5-5.');
    });

    it('starts empty for a profile without data', async () => {
      await setup();

      expect(value('body-birth-year')).toBe('');
      expect(value('body-sex')).toBe('');
      expect(value('body-weight')).toBe('');
      expect(value('body-resting-hr')).toBe('');
      expect(value('body-experience')).toBe('');
      expect(panel.querySelectorAll('input[type="checkbox"]:checked').length).toBe(0);
    });

    it('starts with what is stored', async () => {
      await setup(FULL);

      expect(value('body-birth-year')).toBe('1985');
      expect(value('body-sex')).toBe('female');
      expect(value('body-weight')).toBe('61.5');
      expect(value('body-resting-hr')).toBe('48');
      expect(value('body-years-running')).toBe('12');
      expect(value('body-years-cycling')).toBe('3');
      expect(value('body-years-swimming')).toBe('');
      expect(value('body-years-strength')).toBe('0');
      expect(value('body-experience')).toBe('beginner');
      expect(query<HTMLInputElement>(panel, '#body-equipment-gym').checked).toBe(true);
      expect(query<HTMLInputElement>(panel, '#body-equipment-home').checked).toBe(false);
      expect(query<HTMLInputElement>(panel, '#body-equipment-dumbbells').checked).toBe(true);
    });

    it('offers the choices the server knows', async () => {
      await setup();

      const options = (id: string) =>
        Array.from(panel.querySelectorAll<HTMLOptionElement>(`#${id} option`)).map((o) => o.value);
      expect(options('body-sex')).toEqual(['', 'female', 'male', 'other']);
      expect(options('body-experience')).toEqual(['', 'beginner', 'advanced']);
    });
  });

  describe('saving', () => {
    it('sends every field, an empty one as null', async () => {
      await setup();
      await type('body-weight', '70,5');
      await choose('body-sex', 'male');

      await submit();

      expect(api.saveBody).toHaveBeenCalledExactlyOnceWith({
        birth_year: null,
        sex: 'male',
        weight_kg: 70.5,
        resting_hr: null,
        training_years: { running: null, cycling: null, swimming: null, strength: null },
        strength_experience: null,
        strength_equipment: [],
      });
    });

    it('sends the ticked equipment and the years', async () => {
      await setup();
      query<HTMLInputElement>(panel, '#body-equipment-home').click();
      await type('body-years-running', '7');

      await submit();

      expect(api.saveBody.mock.calls[0][0]).toMatchObject({
        training_years: { running: 7 },
        strength_equipment: ['home'],
      });
    });

    it('clears a field that was emptied', async () => {
      await setup(FULL);
      await type('body-weight', '');

      await submit();

      expect(api.saveBody.mock.calls[0][0]).toMatchObject({ weight_kg: null, birth_year: 1985 });
    });

    it('says so, shows what the server answered and tells the page', async () => {
      await setup();
      const saved = profile({ weight_kg: 70 });
      api.saveBody.mockResolvedValue({ kind: 'ok', profile: saved });
      const emitted: AthleteProfile[] = [];
      fixture.componentInstance.saved.subscribe((p) => emitted.push(p));
      await type('body-weight', '70');

      await submit();

      expect(notice()).toBe('Saved.');
      expect(value('body-weight')).toBe('70');
      expect(emitted).toEqual([saved]);
    });

    it('does not ask the server when a field cannot be used, and names it', async () => {
      await setup();
      await type('body-weight', '5');
      await type('body-resting-hr', 'fast');
      await type('body-years-running', '99');

      await submit();

      expect(api.saveBody).not.toHaveBeenCalled();
      expect(alerts()).toEqual([
        'Enter a weight between 25 and 300 kg.',
        'Enter a resting heart rate between 25 and 120 bpm.',
        'Enter whole years between 0 and 80.',
      ]);
      expect(query(panel, '#body-weight').getAttribute('aria-invalid')).toBe('true');
    });

    it('takes a message away once the field is fixed', async () => {
      await setup();
      await type('body-weight', '5');
      await submit();
      await type('body-weight', '70');

      await submit();

      expect(alerts()).toEqual([]);
      expect(api.saveBody).toHaveBeenCalledTimes(1);
    });

    it('shows the server’s messages next to their fields', async () => {
      await setup();
      api.saveBody.mockResolvedValue({
        kind: 'invalid',
        errors: ['Bad weight.', 'Bad years.'],
        fields: { weight_kg: ['Bad weight.'], training_years: ['Bad years.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Bad weight.', 'Bad years.']);
      expect(query(panel, '#body-weight').getAttribute('aria-invalid')).toBe('true');
    });

    it('shows a message that no field owns above the form, once', async () => {
      await setup();
      api.saveBody.mockResolvedValue({
        kind: 'invalid',
        errors: ['Something general.'],
        fields: { non_field_errors: ['Something general.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Something general.']);
    });

    it('says something went wrong when the request fails', async () => {
      await setup();
      api.saveBody.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('tells the page when the session is gone', async () => {
      await setup();
      api.saveBody.mockResolvedValue({ kind: 'forbidden' });
      let gone = 0;
      fixture.componentInstance.signedOut.subscribe(() => gone++);

      await submit();

      expect(gone).toBe(1);
    });

    it('does one thing at a time', async () => {
      await setup();
      const slow = deferred<SaveBodyResult>();
      api.saveBody.mockReturnValue(slow.promise);

      void submit();
      await settle(fixture);
      await submit();

      expect(api.saveBody).toHaveBeenCalledTimes(1);
      slow.resolve({ kind: 'ok', profile: profile() });
      await settle(fixture);
    });
  });
});
