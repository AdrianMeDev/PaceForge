import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { SetupKey, SetupStep } from '../../core/dashboard/dashboard-models';
import { query } from '../../testing/dom';
import {
  HIDDEN_KEY,
  STEP_INFO,
  SetupChecklist,
  readHidden,
  setupComplete,
  writeHidden,
} from './setup-checklist';

const ORDER: SetupKey[] = [
  'profile',
  'training_time',
  'ai_coach',
  'intervals',
  'goal',
  'activities',
  'season',
  'first_week',
];

function steps(done: SetupKey[] = []): SetupStep[] {
  return ORDER.map((key) => ({ key, done: done.includes(key), optional: key === 'intervals' }));
}

describe('SetupChecklist', () => {
  let fixture: ComponentFixture<SetupChecklist>;
  let hidden: number;

  function show(list: SetupStep[]): HTMLElement {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    fixture = TestBed.createComponent(SetupChecklist);
    fixture.componentRef.setInput('steps', list);
    hidden = 0;
    fixture.componentInstance.hide.subscribe(() => hidden++);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  it('lists the steps in order, each with its title', () => {
    const page = show(steps());

    const titles = Array.from(page.querySelectorAll('ol li p.font-semibold')).map((p) =>
      p.childNodes[0].textContent?.trim(),
    );
    expect(titles).toEqual(ORDER.map((key) => STEP_INFO[key].title));
  });

  it('counts only the steps that are not optional', () => {
    const page = show(steps(['profile', 'goal', 'intervals']));

    expect(query(page, '[data-testid="setup-count"]').textContent?.trim()).toBe('2 of 7 done');
  });

  it('marks a step that is done and gives it no button', () => {
    const page = show(steps(['profile']));

    const done = query(page, '[data-testid="setup-profile"]');
    expect(done.getAttribute('data-done')).toBe('true');
    expect(done.querySelector('a')).toBeNull();
    expect(done.textContent).toContain('(done)');
  });

  it('gives a step that is open a button to its page', () => {
    const page = show(steps(['profile']));

    const link = query<HTMLAnchorElement>(page, '[data-testid="setup-goal"] a');
    expect(link.getAttribute('href')).toBe('/goals');
    expect(link.textContent?.trim()).toBe(STEP_INFO.goal.action);
    expect(query(page, '[data-testid="setup-goal"]').textContent).toContain('(to do)');
  });

  it('marks the optional step', () => {
    const page = show(steps());

    expect(query(page, '[data-testid="setup-intervals"] .badge').textContent?.trim()).toBe(
      'optional',
    );
    expect(page.querySelectorAll('.badge')).toHaveLength(1);
  });

  it('says that the user wants it gone', () => {
    const page = show(steps());

    query<HTMLButtonElement>(page, 'button').click();

    expect(hidden).toBe(1);
  });
});

describe('setupComplete', () => {
  it('needs every step that is not optional', () => {
    expect(setupComplete(steps(ORDER.filter((key) => key !== 'intervals')))).toBe(true);
    expect(setupComplete(steps(['profile']))).toBe(false);
  });

  it('is true for no steps at all', () => {
    expect(setupComplete([])).toBe(true);
  });
});

describe('the memory of the hidden card', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.localStorage.removeItem(HIDDEN_KEY);
  });

  it('keeps what the user chose', () => {
    expect(readHidden()).toBe(false);

    writeHidden(true);
    expect(readHidden()).toBe(true);

    writeHidden(false);
    expect(readHidden()).toBe(false);
  });

  it('works without any storage: the card is shown and nothing breaks', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(readHidden()).toBe(false);
    expect(() => writeHidden(true)).not.toThrow();
  });
});
