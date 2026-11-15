import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SportPreferences } from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import {
  NO_PREFERENCE_FORM,
  NO_SPORT_TEXTS,
  PreferenceErrors,
  PreferenceForm,
  SESSIONS_ERROR,
  SportPreferencesForm,
  preferenceForm,
  readPreferences,
} from './sport-preferences';

const NONE = { role: null, sessions_min: null, sessions_max: null };
const EMPTY: SportPreferences = { running: NONE, cycling: NONE, swimming: NONE, strength: NONE };

function formWith(sports: Partial<PreferenceForm['sports']>, focus = ''): PreferenceForm {
  return { sports: { ...NO_PREFERENCE_FORM.sports, ...sports }, focus };
}

describe('preferenceForm', () => {
  it('writes null as an empty field and numbers as text', () => {
    const form = preferenceForm(
      { ...EMPTY, running: { role: 'goal', sessions_min: 3, sessions_max: 0 } },
      'legs',
    );

    expect(form.sports.running).toEqual({ role: 'goal', min: '3', max: '0' });
    expect(form.sports.cycling).toEqual(NO_SPORT_TEXTS);
    expect(form.focus).toBe('legs');
  });

  it('writes no focus as an empty choice', () => {
    expect(preferenceForm(EMPTY, null)).toEqual(NO_PREFERENCE_FORM);
  });
});

describe('readPreferences', () => {
  it('reads an empty form as nothing said for every sport', () => {
    expect(readPreferences(NO_PREFERENCE_FORM)).toEqual({
      ok: true,
      preferences: EMPTY,
      focus: null,
    });
  });

  it('reads roles, counts and the focus', () => {
    const result = readPreferences(
      formWith(
        {
          running: { role: 'goal', min: '3', max: ' 5 ' },
          strength: { role: 'supplementary', min: '', max: '2' },
        },
        'full_body',
      ),
    );

    expect(result).toEqual({
      ok: true,
      focus: 'full_body',
      preferences: {
        ...EMPTY,
        running: { role: 'goal', sessions_min: 3, sessions_max: 5 },
        strength: { role: 'supplementary', sessions_min: null, sessions_max: 2 },
      },
    });
  });

  it('accepts a zero and the ends of the range', () => {
    const result = readPreferences(formWith({ cycling: { role: '', min: '0', max: '14' } }));

    expect(result).toMatchObject({
      ok: true,
      preferences: { cycling: { role: null, sessions_min: 0, sessions_max: 14 } },
    });
  });

  it.each(['15', '99', '-1', '1.5', 'two', '1e1', '100'])('refuses %j as a count', (text) => {
    expect(readPreferences(formWith({ running: { role: '', min: text, max: '' } }))).toEqual({
      ok: false,
      errors: { running: SESSIONS_ERROR },
    });
    expect(readPreferences(formWith({ swimming: { role: '', min: '', max: text } }))).toEqual({
      ok: false,
      errors: { swimming: SESSIONS_ERROR },
    });
  });

  it('refuses a least above the most', () => {
    expect(readPreferences(formWith({ running: { role: '', min: '5', max: '3' } }))).toEqual({
      ok: false,
      errors: { running: SESSIONS_ERROR },
    });
  });

  it('accepts equal counts', () => {
    expect(readPreferences(formWith({ running: { role: '', min: '3', max: '3' } })).ok).toBe(true);
  });

  it('names every sport that is wrong at once', () => {
    const result = readPreferences(
      formWith({
        running: { role: '', min: 'x', max: '' },
        strength: { role: '', min: '', max: '99' },
      }),
    );

    expect(result.ok ? [] : Object.keys(result.errors)).toEqual(['running', 'strength']);
  });
});

@Component({
  imports: [SportPreferencesForm],
  template: `<app-sport-preferences [(form)]="form" [errors]="errors()" [message]="message()" />`,
})
class Host {
  readonly form = signal<PreferenceForm>(NO_PREFERENCE_FORM);
  readonly errors = signal<PreferenceErrors>({});
  readonly message = signal<string | null>(null);
}

describe('SportPreferencesForm', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let element: HTMLElement;

  beforeEach(async () => {
    TestBed.configureTestingModule({ imports: [Host] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    element = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  });

  const select = (id: string) => query<HTMLSelectElement>(element, `#${id}`);

  async function choose(id: string, value: string): Promise<void> {
    const box = select(id);
    box.value = value;
    box.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  it('has a row for every sport and a choice for the focus', () => {
    const rows = Array.from(element.querySelectorAll('tbody tr'));

    expect(rows.map((row) => row.querySelector('th')?.textContent?.trim())).toEqual([
      'Running',
      'Cycling',
      'Swimming',
      'Strength / gym',
    ]);
    expect(Array.from(select('role-running').options).map((o) => o.value)).toEqual([
      '',
      'goal',
      'secondary',
      'supplementary',
    ]);
    expect(Array.from(select('strength-focus').options).map((o) => o.value)).toEqual([
      '',
      'legs',
      'core',
      'upper_body',
      'full_body',
    ]);
  });

  it('names every box for a screen reader', () => {
    expect(select('role-cycling').getAttribute('aria-label')).toBe('Cycling, role');
    expect(query(element, '#min-strength').getAttribute('aria-label')).toBe(
      'Strength / gym, least sessions',
    );
    expect(query(element, '#max-running').getAttribute('aria-label')).toBe(
      'Running, most sessions',
    );
  });

  it('shows the values it is given', async () => {
    host.form.set(formWith({ running: { role: 'secondary', min: '2', max: '4' } }, 'core'));
    await settle(fixture);

    expect(select('role-running').value).toBe('secondary');
    expect(query<HTMLInputElement>(element, '#min-running').value).toBe('2');
    expect(query<HTMLInputElement>(element, '#max-running').value).toBe('4');
    expect(select('strength-focus').value).toBe('core');
  });

  it('hands every change to the page, sport by sport', async () => {
    await choose('role-cycling', 'goal');
    typeInto(element, '#min-cycling', '1');
    typeInto(element, '#max-strength', '2');
    await choose('strength-focus', 'legs');

    expect(host.form().sports.cycling).toEqual({ role: 'goal', min: '1', max: '' });
    expect(host.form().sports.strength).toEqual({ role: '', min: '', max: '2' });
    expect(host.form().sports.running).toEqual(NO_SPORT_TEXTS);
    expect(host.form().focus).toBe('legs');
  });

  it('takes a role back with no role', async () => {
    host.form.set(formWith({ running: { role: 'goal', min: '', max: '' } }));
    await settle(fixture);

    await choose('role-running', '');

    expect(host.form().sports.running.role).toBe('');
  });

  it('shows a message under its sport and marks the numbers', async () => {
    host.errors.set({ swimming: SESSIONS_ERROR });
    await settle(fixture);

    expect(query(element, '#preference-swimming-error').textContent?.trim()).toBe(
      `Swimming: ${SESSIONS_ERROR}`,
    );
    expect(query(element, '#min-swimming').getAttribute('aria-invalid')).toBe('true');
    expect(query(element, '#max-swimming').getAttribute('aria-invalid')).toBe('true');
    expect(query(element, '#min-running').getAttribute('aria-invalid')).toBeNull();
  });

  it('shows the server’s message as a whole above the table', async () => {
    host.message.set('Choose one of: legs, core, upper_body, full_body.');
    await settle(fixture);

    expect(element.querySelector('[role="alert"]')?.textContent?.trim()).toBe(
      'Choose one of: legs, core, upper_body, full_body.',
    );
  });
});
