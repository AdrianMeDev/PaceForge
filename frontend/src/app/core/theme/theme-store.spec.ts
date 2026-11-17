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

  describe('what is shown', () => {
    let listeners: ((event: { matches: boolean }) => void)[];

    function device(dark: boolean) {
      listeners = [];
      vi.stubGlobal(
        'matchMedia',
        vi.fn(() => ({
          matches: dark,
          addEventListener: (_: string, listener: (event: { matches: boolean }) => void) =>
            listeners.push(listener),
        })),
      );
    }

    afterEach(() => vi.unstubAllGlobals());

    it("is the device's setting while none is chosen", () => {
      device(true);
      store().initialize();

      expect(store().shown()).toBe('dark');
    });

    it('is the choice once there is one', () => {
      device(true);
      store().initialize();

      store().set('light');

      expect(store().shown()).toBe('light');
    });

    it('follows the device when it changes by itself', () => {
      device(false);
      store().initialize();
      expect(store().shown()).toBe('light');

      listeners.forEach((listener) => listener({ matches: true }));

      expect(store().shown()).toBe('dark');
    });

    it('is light without a way to ask the device', () => {
      vi.stubGlobal('matchMedia', undefined);
      store().initialize();

      expect(store().shown()).toBe('light');
    });

    it("toggles from the device's dark to light and keeps that choice", () => {
      device(true);
      store().initialize();

      store().toggle();

      expect(store().choice()).toBe('light');
      expect(localStorage.getItem(THEME_KEY)).toBe('light');
    });

    it("toggles from the device's light to dark, and back", () => {
      device(false);
      store().initialize();

      store().toggle();
      expect(store().choice()).toBe('dark');
      store().toggle();
      expect(store().choice()).toBe('light');
    });
  });
});
