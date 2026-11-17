import { TestBed } from '@angular/core/testing';
import { THEME_KEY, ThemeStore } from './theme-store';

describe('ThemeStore', () => {
  const root = document.documentElement;

  beforeEach(() => {
    localStorage.clear();
    root.removeAttribute('data-theme');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    root.removeAttribute('data-theme');
  });

  function store(): ThemeStore {
    return TestBed.inject(ThemeStore);
  }

  it('follows the device by default and shows no attribute', () => {
    store().initialize();

    expect(store().choice()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBe(false);
  });

  it.each(['light', 'dark'] as const)('shows the choice %s and keeps it', (choice) => {
    store().initialize();

    store().set(choice);

    expect(store().choice()).toBe(choice);
    expect(root.getAttribute('data-theme')).toBe(choice);
    expect(localStorage.getItem(THEME_KEY)).toBe(choice);
  });

  it('goes back to the device and forgets the choice', () => {
    store().initialize();
    store().set('dark');

    store().set('system');

    expect(root.hasAttribute('data-theme')).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it('reads a stored choice when the app starts', () => {
    localStorage.setItem(THEME_KEY, 'dark');

    store().initialize();

    expect(store().choice()).toBe('dark');
    expect(root.getAttribute('data-theme')).toBe('dark');
  });

  it.each(['', 'blue', 'DARK', 'system', '{}'])('ignores the stored value %j', (value) => {
    localStorage.setItem(THEME_KEY, value);

    store().initialize();

    expect(store().choice()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBe(false);
  });

  it('ignores a choice that is none of the three', () => {
    store().initialize();

    store().set('blue' as never);

    expect(store().choice()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBe(false);
  });

  it('works without storage: it reads the device and the choice lasts for the visit', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    store().initialize();
    expect(store().choice()).toBe('system');

    store().set('dark');
    expect(store().choice()).toBe('dark');
    expect(root.getAttribute('data-theme')).toBe('dark');
  });
});
