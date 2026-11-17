import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ThemeStore } from '../../core/theme/theme-store';
import { query } from '../../testing/dom';
import { AppearancePanel } from './appearance-panel';

describe('AppearancePanel', () => {
  let fixture: ComponentFixture<AppearancePanel>;
  let page: HTMLElement;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ imports: [AppearancePanel] });
    TestBed.inject(ThemeStore).initialize();
    fixture = TestBed.createComponent(AppearancePanel);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  const radios = () => Array.from(page.querySelectorAll<HTMLInputElement>('input[type="radio"]'));

  it('is a labelled group of three choices', () => {
    expect(query(page, 'legend').textContent).toBe('Appearance');
    expect(radios().map((radio) => radio.value)).toEqual(['system', 'light', 'dark']);
    expect(Array.from(page.querySelectorAll('label')).map((l) => l.textContent?.trim())).toEqual([
      'Match my device',
      'Light',
      'Dark',
    ]);
    expect(new Set(radios().map((radio) => radio.name)).size).toBe(1);
  });

  it('starts on the device', () => {
    expect(radios().map((radio) => radio.checked)).toEqual([true, false, false]);
  });

  it('shows and keeps a choice at once', async () => {
    radios()[2].click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('paceforge.theme')).toBe('dark');
    expect(radios().map((radio) => radio.checked)).toEqual([false, false, true]);
  });

  it('goes back to the device', async () => {
    radios()[1].click();
    await fixture.whenStable();
    radios()[0].click();
    await fixture.whenStable();

    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(localStorage.getItem('paceforge.theme')).toBeNull();
  });

  it('says where the choice is kept', () => {
    expect(page.textContent).toContain('kept in this browser only');
  });
});
