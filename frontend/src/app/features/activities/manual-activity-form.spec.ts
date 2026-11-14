import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivitiesApi } from '../../core/activities/activities-api';
import {
  Activity,
  EnterActivityResult,
  ManualActivityInput,
} from '../../core/activities/activities-models';
import { query, settle, typeInto } from '../../testing/dom';
import { ManualActivityForm } from './manual-activity-form';

const SAVED: Activity = {
  id: 'n1',
  source: 'manual',
  sport: 'strength',
  source_sport: '',
  start_time: '2026-11-12T06:30:00Z',
  elapsed_seconds: null,
  timer_seconds: 2700,
  distance_m: null,
  avg_heart_rate: null,
  max_heart_rate: null,
  avg_power_w: null,
  total_ascent_m: null,
  calories: null,
  manufacturer: '',
  rpe: 7,
  notes: '',
  load: 315,
  created_at: '2026-11-14T07:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('ManualActivityForm', () => {
  let enter: ReturnType<typeof vi.fn<(input: ManualActivityInput) => Promise<EnterActivityResult>>>;
  let fixture: ComponentFixture<ManualActivityForm>;
  let page: HTMLElement;
  const entered = vi.fn();
  const signedOut = vi.fn();
  const located = vi.fn();

  async function setup(inputs: { listed?: string[]; disabled?: boolean } = {}) {
    enter = vi.fn<(input: ManualActivityInput) => Promise<EnterActivityResult>>();
    entered.mockClear();
    signedOut.mockClear();
    located.mockClear();
    TestBed.configureTestingModule({
      imports: [ManualActivityForm],
      providers: [{ provide: ActivitiesApi, useValue: { enter } }],
    });
    fixture = TestBed.createComponent(ManualActivityForm);
    fixture.componentRef.setInput('listedIds', inputs.listed ?? []);
    fixture.componentRef.setInput('disabled', inputs.disabled ?? false);
    fixture.componentInstance.entered.subscribe(entered);
    fixture.componentInstance.signedOut.subscribe(signedOut);
    fixture.componentInstance.locate.subscribe(located);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const byId = (id: string) => page.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const errorTexts = () =>
    Array.from(page.querySelectorAll('.field-error')).map((e) => e.textContent?.trim());
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(page, selector).value;

  /** Types as a user does: the browser renders after every keystroke, so the test does too. */
  function type(selector: string, text: string): void {
    typeInto(page, selector, text);
    fixture.detectChanges();
  }

  function choose(selector: string, chosen: string): void {
    const select = query<HTMLSelectElement>(page, selector);
    select.value = chosen;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  async function save(): Promise<void> {
    query<HTMLButtonElement>(page, '[data-testid="manual-save"]').click();
    await settle(fixture);
  }

  /** The minimum the form needs: the duration (the rest has defaults). */
  function fill(duration = '45'): void {
    type('#manual-date', '2026-11-12');
    type('#manual-time', '06:30');
    type('#manual-duration', duration);
  }

  it('starts with today, the time now and strength as the sport', async () => {
    await setup();

    expect(value('#manual-sport')).toBe('strength');
    expect(value('#manual-date')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(value('#manual-time')).toMatch(/^\d{2}:\d{2}$/);
    expect(value('#manual-duration')).toBe('');
  });

  it('offers the five sports and the ratings 1 to 10 after an empty choice', async () => {
    await setup();

    expect(
      Array.from(page.querySelectorAll('#manual-sport option')).map((o) => o.textContent?.trim()),
    ).toEqual(['Running', 'Cycling', 'Swimming', 'Strength', 'Other']);
    const ratings = Array.from(page.querySelectorAll('#manual-rpe option'));
    expect(ratings).toHaveLength(11);
    expect(ratings[0].textContent?.trim()).toBe('–');
    expect(ratings[10].textContent?.trim()).toBe('10 – Maximal');
  });

  it('sends what was entered and says that it was saved', async () => {
    await setup();
    enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
    choose('#manual-sport', 'running');
    fill('45');
    type('#manual-distance', '5,5');
    choose('#manual-rpe', '7');
    type('#manual-notes', '  Legs were heavy  ');

    await save();

    expect(enter).toHaveBeenCalledExactlyOnceWith({
      sport: 'running',
      date: '2026-11-12',
      time: '06:30',
      duration_minutes: 45,
      distance_km: 5.5,
      rpe: 7,
      notes: 'Legs were heavy',
    });
    expect(byId('manual-saved')?.textContent).toContain('The session was saved.');
    expect(entered).toHaveBeenCalledTimes(1);
  });

  it('sends no distance and no rating if none was entered', async () => {
    await setup();
    enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
    fill();

    await save();

    expect(enter).toHaveBeenCalledWith(
      expect.objectContaining({ distance_km: null, rpe: null, notes: '' }),
    );
  });

  it('clears the entries of the session but keeps sport and day', async () => {
    await setup();
    enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
    choose('#manual-sport', 'cycling');
    fill();
    type('#manual-distance', '30');
    choose('#manual-rpe', '4');
    type('#manual-notes', 'x');

    await save();

    expect(value('#manual-duration')).toBe('');
    expect(value('#manual-distance')).toBe('');
    expect(value('#manual-rpe')).toBe('');
    expect(value('#manual-notes')).toBe('');
    expect(value('#manual-sport')).toBe('cycling');
    expect(value('#manual-date')).toBe('2026-11-12');
  });

  describe('what is checked before anything is sent', () => {
    it.each([
      ['an empty duration', '', 'Enter how long the session was, in minutes.'],
      ['a duration of 0', '0', 'Enter whole minutes from 1 to 1440.'],
      ['a duration above a day', '1441', 'Enter whole minutes from 1 to 1440.'],
      ['a duration in hours', '1:30', 'Enter whole minutes from 1 to 1440.'],
    ])('refuses %s', async (_name, text, message) => {
      await setup();
      fill(text);

      await save();

      expect(errorTexts()).toEqual([message]);
      expect(enter).not.toHaveBeenCalled();
      expect(query(page, '#manual-duration').getAttribute('aria-invalid')).toBe('true');
    });

    it('refuses a distance that is no distance', async () => {
      await setup();
      fill();
      type('#manual-distance', 'far');

      await save();

      expect(errorTexts()).toEqual(['Enter kilometres from 0 to 1000, such as 5.5.']);
      expect(enter).not.toHaveBeenCalled();
    });

    it('refuses a missing day and a missing time', async () => {
      await setup();
      fill();
      type('#manual-date', '');
      type('#manual-time', '');

      await save();

      expect(errorTexts()).toEqual([
        'Enter the day of the session.',
        'Enter the time the session started.',
      ]);
      expect(enter).not.toHaveBeenCalled();
    });

    it('refuses a note that is too long', async () => {
      await setup();
      fill();
      type('#manual-notes', 'x'.repeat(501));

      await save();

      expect(errorTexts()).toEqual(['Use at most 500 characters.']);
      expect(enter).not.toHaveBeenCalled();
    });

    it('reports every problem at once and keeps the entries', async () => {
      await setup();
      type('#manual-duration', '0');
      type('#manual-distance', 'far');

      await save();

      expect(errorTexts()).toHaveLength(2);
      expect(value('#manual-duration')).toBe('0');
      expect(value('#manual-distance')).toBe('far');
    });

    it('takes the messages away when the entry is right', async () => {
      await setup();
      fill('0');
      await save();
      enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
      type('#manual-duration', '45');

      await save();

      expect(errorTexts()).toEqual([]);
      expect(enter).toHaveBeenCalledTimes(1);
    });
  });

  describe('what the server says', () => {
    it('shows its messages next to the fields and keeps the entries', async () => {
      await setup();
      fill('45');
      type('#manual-notes', 'keep me');
      enter.mockResolvedValue({
        kind: 'invalid',
        errors: { date: ['The session cannot start in the future.'], rpe: ['Bad.', 'Worse.'] },
        message: null,
      });

      await save();

      expect(errorTexts()).toEqual(['The session cannot start in the future.', 'Bad.']);
      expect(value('#manual-notes')).toBe('keep me');
      expect(value('#manual-duration')).toBe('45');
      expect(entered).not.toHaveBeenCalled();
    });

    it('shows a message that belongs to no field above the button', async () => {
      await setup();
      fill();
      enter.mockResolvedValue({ kind: 'invalid', errors: {}, message: 'JSON parse error' });

      await save();

      expect(byId('manual-message')?.textContent).toContain('JSON parse error');
    });

    it('says that the session is there already and offers it if it is listed', async () => {
      await setup({ listed: ['n9'] });
      fill();
      enter.mockResolvedValue({ kind: 'duplicate', existingId: 'n9' });

      await save();

      expect(byId('manual-message')?.textContent).toContain('You already have this session.');
      query<HTMLButtonElement>(page, '[data-testid="manual-locate"]').click();
      expect(located).toHaveBeenCalledExactlyOnceWith('n9');
      expect(value('#manual-duration')).toBe('45');
      expect(entered).not.toHaveBeenCalled();
    });

    it('does not offer a session that is not in the list', async () => {
      await setup({ listed: ['other'] });
      fill();
      enter.mockResolvedValue({ kind: 'duplicate', existingId: 'n9' });

      await save();

      expect(byId('manual-message')?.textContent).toContain('You already have this session.');
      expect(byId('manual-locate')).toBeNull();
    });

    it('says when too much was entered in a short time', async () => {
      await setup();
      fill();
      enter.mockResolvedValue({ kind: 'rate_limited' });

      await save();

      expect(byId('manual-message')?.textContent).toContain('Too many entries.');
    });

    it('tells the page that the session has ended', async () => {
      await setup();
      fill();
      enter.mockResolvedValue({ kind: 'forbidden' });

      await save();

      expect(signedOut).toHaveBeenCalledTimes(1);
    });

    it('says so when the call fails, and lets the user try again', async () => {
      await setup();
      fill();
      enter.mockRejectedValueOnce(new Error('network'));
      await save();
      expect(byId('manual-message')?.textContent).toContain('Something went wrong.');

      enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
      await save();

      expect(byId('manual-message')).toBeNull();
      expect(entered).toHaveBeenCalledTimes(1);
    });

    it('forgets the last message when it tries again', async () => {
      await setup();
      fill();
      enter.mockResolvedValueOnce({ kind: 'rate_limited' });
      await save();

      enter.mockResolvedValue({ kind: 'entered', activity: SAVED });
      await save();

      expect(byId('manual-message')).toBeNull();
      expect(byId('manual-saved')).not.toBeNull();
    });
  });

  describe('while it works', () => {
    it('sends once and shows that it is saving', async () => {
      await setup();
      fill();
      const pending = deferred<EnterActivityResult>();
      enter.mockReturnValue(pending.promise);

      query<HTMLButtonElement>(page, '[data-testid="manual-save"]').click();
      await settle(fixture);
      query<HTMLButtonElement>(page, '[data-testid="manual-save"]').click();
      await settle(fixture);

      expect(enter).toHaveBeenCalledTimes(1);
      expect(byId('manual-save')?.textContent?.trim()).toBe('Saving…');
      expect((byId('manual-save') as HTMLButtonElement).disabled).toBe(true);

      pending.resolve({ kind: 'entered', activity: SAVED });
      await settle(fixture);
      expect(byId('manual-save')?.textContent?.trim()).toBe('Save session');
    });

    it('does nothing while the page is busy with something else', async () => {
      await setup({ disabled: true });
      fill();

      await save();

      expect((byId('manual-save') as HTMLButtonElement).disabled).toBe(true);
      expect(enter).not.toHaveBeenCalled();
    });
  });
});
