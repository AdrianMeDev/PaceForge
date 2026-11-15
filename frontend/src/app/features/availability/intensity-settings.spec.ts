import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { IntensityLevel, Limits } from '../../core/availability/availability-models';
import { query, settle, typeInto } from '../../testing/dom';
import {
  IntensityErrors,
  IntensitySettings,
  NO_OWN_LIMIT_TEXTS,
  OwnLimitTexts,
  ownLimitTexts,
  readOwnLimits,
} from './intensity-settings';

const LEVEL_LIMITS: Record<IntensityLevel, Limits> = {
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

const texts = (own: Partial<OwnLimitTexts>): OwnLimitTexts => ({ ...NO_OWN_LIMIT_TEXTS, ...own });

describe('readOwnLimits', () => {
  it('reads empty fields as the level’s value', () => {
    expect(readOwnLimits(texts({ max_hard_days: '  ' }), LEVEL_LIMITS.normal)).toEqual({
      ok: true,
      value: {
        max_hard_days: null,
        progression_warning_percent: null,
        progression_error_percent: null,
        easy_share_percent: null,
      },
    });
  });

  it('reads whole numbers, the ends of the ranges included', () => {
    const low = texts({
      max_hard_days: '0',
      progression_warning_percent: '100',
      progression_error_percent: '300',
      easy_share_percent: '50',
    });
    const high = texts({ max_hard_days: ' 4 ', easy_share_percent: '100' });

    expect(readOwnLimits(low, LEVEL_LIMITS.normal)).toEqual({
      ok: true,
      value: {
        max_hard_days: 0,
        progression_warning_percent: 100,
        progression_error_percent: 300,
        easy_share_percent: 50,
      },
    });
    expect(readOwnLimits(high, LEVEL_LIMITS.normal)).toMatchObject({
      ok: true,
      value: { max_hard_days: 4, easy_share_percent: 100 },
    });
  });

  it.each([
    ['max_hard_days', '5', 'Enter a whole number of days between 0 and 4.'],
    ['max_hard_days', '-1', 'Enter a whole number of days between 0 and 4.'],
    ['max_hard_days', '2.5', 'Enter a whole number of days between 0 and 4.'],
    ['max_hard_days', 'two', 'Enter a whole number of days between 0 and 4.'],
    ['progression_warning_percent', '99', 'Enter a whole percent between 100 and 200.'],
    ['progression_warning_percent', '201', 'Enter a whole percent between 100 and 200.'],
    ['progression_error_percent', '301', 'Enter a whole percent between 100 and 300.'],
    ['easy_share_percent', '49', 'Enter a whole percent between 50 and 100.'],
    ['easy_share_percent', '80 %', 'Enter a whole percent between 50 and 100.'],
  ] as const)('refuses %s = %s with the server’s message', (name, text, message) => {
    expect(readOwnLimits(texts({ [name]: text }), LEVEL_LIMITS.normal)).toEqual({
      ok: false,
      errors: { [name]: message },
    });
  });

  it('names every field that is out of range at once', () => {
    const result = readOwnLimits(
      texts({ max_hard_days: '9', easy_share_percent: '10' }),
      LEVEL_LIMITS.normal,
    );

    expect(result.ok ? [] : Object.keys(result.errors)).toEqual([
      'max_hard_days',
      'easy_share_percent',
    ]);
  });

  it('wants the warning below the error, told at the error if both are own', () => {
    expect(
      readOwnLimits(
        texts({ progression_warning_percent: '150', progression_error_percent: '150' }),
        LEVEL_LIMITS.normal,
      ),
    ).toEqual({
      ok: false,
      errors: {
        progression_error_percent:
          'The warning limit (150 %) must be below the error limit (150 %).',
      },
    });
  });

  it('checks an own warning against the level’s error, and the other way round', () => {
    expect(
      readOwnLimits(texts({ progression_warning_percent: '135' }), LEVEL_LIMITS.relaxed),
    ).toEqual({
      ok: false,
      errors: {
        progression_warning_percent:
          'The warning limit (135 %) must be below the error limit (130 %).',
      },
    });
    expect(
      readOwnLimits(texts({ progression_warning_percent: '135' }), LEVEL_LIMITS.normal).ok,
    ).toBe(true);
    expect(
      readOwnLimits(texts({ progression_error_percent: '130' }), LEVEL_LIMITS.intensive),
    ).toEqual({
      ok: false,
      errors: {
        progression_error_percent:
          'The warning limit (130 %) must be below the error limit (130 %).',
      },
    });
  });
});

describe('ownLimitTexts', () => {
  it('writes numbers as they are and null as an empty field', () => {
    expect(
      ownLimitTexts({
        max_hard_days: 0,
        progression_warning_percent: null,
        progression_error_percent: 160,
        easy_share_percent: null,
      }),
    ).toEqual({
      max_hard_days: '0',
      progression_warning_percent: '',
      progression_error_percent: '160',
      easy_share_percent: '',
    });
  });
});

@Component({
  imports: [IntensitySettings],
  template: `<app-intensity-settings
    [(level)]="level"
    [(own)]="own"
    [levelLimits]="limits"
    [errors]="errors()"
  />`,
})
class Host {
  readonly level = signal<IntensityLevel>('normal');
  readonly own = signal<OwnLimitTexts>(NO_OWN_LIMIT_TEXTS);
  readonly limits = LEVEL_LIMITS;
  readonly errors = signal<IntensityErrors>({});
}

describe('IntensitySettings', () => {
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

  const radio = (level: IntensityLevel) => query<HTMLInputElement>(element, `#level-${level}`);
  const field = (name: string) => query<HTMLInputElement>(element, `#limit-${name}`);
  const details = () => query<HTMLDetailsElement>(element, 'details');

  it('shows the three levels with their limits and the chosen one ticked', () => {
    expect(radio('normal').checked).toBe(true);
    expect(radio('relaxed').checked).toBe(false);
    expect(query(element, '#level-relaxed-limits').textContent?.trim()).toBe(
      '1 hard day a week, at least 85 % easy; a warning above 115 % of your usual week, an error above 130 %.',
    );
    expect(query(element, '#level-intensive-limits').textContent).toContain('3 hard days a week');
  });

  it('changes the level', async () => {
    radio('intensive').click();
    await settle(fixture);

    expect(host.level()).toBe('intensive');
  });

  it('shows the values of the chosen level where no own value is given', async () => {
    expect(field('max_hard_days').placeholder).toBe('2');
    expect(field('easy_share_percent').placeholder).toBe('80');

    host.level.set('relaxed');
    await settle(fixture);

    expect(field('max_hard_days').placeholder).toBe('1');
    expect(field('progression_error_percent').placeholder).toBe('130');
  });

  it('keeps the own limits closed until there are some', async () => {
    expect(details().open).toBe(false);

    host.own.set(texts({ max_hard_days: '3' }));
    await settle(fixture);

    expect(details().open).toBe(true);
    expect(field('max_hard_days').value).toBe('3');
  });

  it('hands what is typed to the page, field by field', async () => {
    typeInto(element, '#limit-progression_warning_percent', '125');
    await settle(fixture);

    expect(host.own()).toEqual(texts({ progression_warning_percent: '125' }));
  });

  it('shows a message next to its field and opens the own limits for it', async () => {
    host.errors.set({ easy_share_percent: 'Enter a whole percent between 50 and 100.' });
    await settle(fixture);

    expect(details().open).toBe(true);
    expect(field('easy_share_percent').getAttribute('aria-invalid')).toBe('true');
    expect(query(element, '#limit-easy_share_percent-error').textContent?.trim()).toBe(
      'Enter a whole percent between 50 and 100.',
    );
    expect(field('max_hard_days').getAttribute('aria-invalid')).toBeNull();
  });

  it('shows a message about the level below the levels', async () => {
    host.errors.set({ intensity_level: 'Choose one of: relaxed, normal, intensive.' });
    await settle(fixture);

    expect(element.querySelector('fieldset [role="alert"]')?.textContent?.trim()).toBe(
      'Choose one of: relaxed, normal, intensive.',
    );
    expect(radio('normal').getAttribute('aria-invalid')).toBe('true');
  });
});
