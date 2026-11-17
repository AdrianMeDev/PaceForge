import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';
import { ADA, createAuthStoreStub } from '../core/auth/testing/auth-store-stub';
import { Shell } from './shell';
import { NAV_GROUPS } from './navigation';
import { query } from '../testing/dom';

@Component({ template: '' })
class Blank {}

describe('Shell', () => {
  // jsdom has no modal dialog: this is what the browser does that the shell relies on.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open');
        this.dispatchEvent(new Event('close'));
      }
    };
  });

  async function setup(user = ADA) {
    const store = createAuthStoreStub();
    store.signIn(user);
    TestBed.configureTestingModule({
      imports: [Shell],
      providers: [
        provideRouter([
          ...NAV_GROUPS.flatMap((group) => group.items).map((item) => ({
            path: item.path.replace(/^\//, ''),
            pathMatch: item.exact ? ('full' as const) : ('prefix' as const),
            component: Blank,
          })),
        ]),
        { provide: AuthStore, useValue: store },
      ],
    });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Shell);
    await fixture.whenStable();
    return { store, navigate, fixture, page: fixture.nativeElement as HTMLElement };
  }

  async function open(
    fixture: { whenStable(): Promise<unknown> },
    navigate: { mockRestore(): void },
    url: string,
  ) {
    navigate.mockRestore(); // these tests need real navigation
    await TestBed.inject(Router).navigateByUrl(url);
    await fixture.whenStable();
  }

  const groups = (page: HTMLElement) =>
    Array.from(page.querySelectorAll<HTMLElement>('nav[aria-label="Main"] [data-group]')).map(
      (group) => [
        group.getAttribute('data-group'),
        Array.from(group.querySelectorAll<HTMLAnchorElement>('a')).map((a) => [
          (a.textContent ?? '').trim(),
          a.getAttribute('href'),
        ]),
      ],
    );

  const current = (page: HTMLElement) =>
    Array.from(page.querySelectorAll('nav[aria-label="Main"] a[aria-current="page"]')).map((a) =>
      (a.textContent ?? '').trim(),
    );

  it('shows the logo and the name as a link to the start page', async () => {
    const { page } = await setup();

    const brand = page.querySelector<HTMLAnchorElement>('[data-testid="brand"]');
    expect(brand?.getAttribute('href')).toBe('/');
    expect(brand?.textContent?.trim()).toBe('PaceForge');
    // The name is next to it, so the picture says nothing of its own.
    expect(brand?.querySelector('img')?.getAttribute('alt')).toBe('');
  });

  it('shows the display name of the signed-in user', async () => {
    const { page } = await setup();

    expect(page.querySelector('[data-testid="user-label"]')?.textContent).toBe('Ada');
  });

  it('falls back to the email address when there is no display name', async () => {
    const { page } = await setup({ ...ADA, display_name: '' });

    expect(page.querySelector('[data-testid="user-label"]')?.textContent).toBe('ada@example.com');
  });

  it('signs out and returns to the login', async () => {
    const { store, navigate, fixture, page } = await setup();

    query<HTMLButtonElement>(page, '[data-testid="sign-out"]').click();
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();

    expect(store.logout).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  describe('navigation', () => {
    const MEMBER = [
      [
        'Training',
        [
          ['Dashboard', '/'],
          ['Week plan', '/planning'],
          ['Week review', '/review'],
          ['Activities', '/activities'],
        ],
      ],
      [
        'Planning',
        [
          ['Season', '/season'],
          ['Goals', '/goals'],
          ['Training time', '/availability'],
        ],
      ],
      [
        'Settings',
        [
          ['Profile', '/settings/profile'],
          ['Connections', '/settings/connections'],
          ['Security', '/settings/security'],
        ],
      ],
    ];

    it('is a labelled navigation with the pages in three groups', async () => {
      const { page } = await setup();

      expect(page.querySelector('nav[aria-label="Main"]')?.getAttribute('aria-label')).toBe('Main');
      expect(groups(page)).toEqual(MEMBER);
    });

    it('names every group with a heading', async () => {
      const { page } = await setup();

      expect(
        Array.from(page.querySelectorAll('nav[aria-label="Main"] h2')).map((h) =>
          h.textContent?.trim(),
        ),
      ).toEqual(['Training', 'Planning', 'Settings']);
    });

    it('shows the invitations in a group of their own to administrators', async () => {
      const { page } = await setup({ ...ADA, is_staff: true, mfa_enabled: true });

      expect(groups(page)).toEqual([...MEMBER, ['Admin', [['Invitations', '/admin/invitations']]]]);
    });

    it('does not show the invitations to members', async () => {
      const { page } = await setup({ ...ADA, mfa_enabled: true });

      expect(page.textContent).not.toContain('Invitations');
    });

    it('shows the invitations to an administrator who still has to set up two-factor', async () => {
      const { page } = await setup({ ...ADA, is_staff: true, mfa_setup_required: true });

      expect(page.textContent).toContain('Invitations');
    });

    it('draws an icon for every page and gives the link its label as a tooltip', async () => {
      const { page } = await setup();

      const links = Array.from(
        page.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Main"] a'),
      );
      expect(links.length).toBe(10);
      for (const link of links) {
        expect(link.querySelector('app-icon svg')).toBeTruthy();
        expect(link.getAttribute('title')).toBe((link.textContent ?? '').trim());
      }
    });

    it.each(NAV_GROUPS.flatMap((group) => group.items).map((item) => [item.label, item.path]))(
      'marks %s while that page is open and nothing else',
      async (label, path) => {
        const { fixture, page, navigate } = await setup({ ...ADA, is_staff: true });
        await open(fixture, navigate, path);

        expect(current(page)).toEqual([label]);
      },
    );

    it('does not mark the dashboard while another page is open', async () => {
      const { fixture, page, navigate } = await setup();
      await open(fixture, navigate, '/settings/security');

      expect(query(page, 'nav[aria-label="Main"] a').classList.contains('active')).toBe(false);
    });
  });

  describe('tab bar', () => {
    const tabs = (page: HTMLElement) =>
      Array.from(page.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Shortcuts"] a'));

    it('holds the four pages used every day, with an icon and a label each', async () => {
      const { page } = await setup();

      expect(tabs(page).map((a) => [(a.textContent ?? '').trim(), a.getAttribute('href')])).toEqual(
        [
          ['Dashboard', '/'],
          ['Week plan', '/planning'],
          ['Week review', '/review'],
          ['Activities', '/activities'],
        ],
      );
      expect(tabs(page).every((a) => a.querySelector('app-icon svg'))).toBe(true);
    });

    it('is the same for administrators', async () => {
      const { page } = await setup({ ...ADA, is_staff: true });

      expect(tabs(page).length).toBe(4);
    });

    it('marks the page that is open, and only that', async () => {
      const { fixture, page, navigate } = await setup();
      await open(fixture, navigate, '/review');

      const marked = tabs(page).filter((a) => a.getAttribute('aria-current') === 'page');
      expect(marked.map((a) => (a.textContent ?? '').trim())).toEqual(['Week review']);
    });

    it('marks nothing while a page that is not in the bar is open', async () => {
      const { fixture, page, navigate } = await setup();
      await open(fixture, navigate, '/goals');

      expect(tabs(page).some((a) => a.hasAttribute('aria-current'))).toBe(false);
    });
  });

  describe('sheet', () => {
    const more = (page: HTMLElement) => query<HTMLButtonElement>(page, '[data-testid="more"]');
    const sheet = (page: HTMLElement) => query<HTMLDialogElement>(page, '[data-testid="sheet"]');
    const flush = async (fixture: { whenStable(): Promise<unknown> }) => {
      await new Promise((resolve) => setTimeout(resolve));
      await fixture.whenStable();
    };

    it('is closed until "More" is pressed, and "More" says it opens a dialog', async () => {
      const { page } = await setup();

      expect(sheet(page).open).toBe(false);
      expect(more(page).getAttribute('aria-haspopup')).toBe('dialog');
      expect(more(page).getAttribute('aria-expanded')).toBe('false');
    });

    it('opens from "More" and says so', async () => {
      const { fixture, page } = await setup();

      more(page).click();
      await flush(fixture);

      expect(sheet(page).open).toBe(true);
      expect(more(page).getAttribute('aria-expanded')).toBe('true');
      expect(sheet(page).getAttribute('aria-labelledby')).toBe('sheet-title');
    });

    it('holds the groups that are not in the tab bar, and the user', async () => {
      const { page } = await setup();

      const links = Array.from(page.querySelectorAll('[data-testid="sheet"] a')).map((a) =>
        (a.textContent ?? '').trim(),
      );
      expect(links).toEqual([
        'Season',
        'Goals',
        'Training time',
        'Profile',
        'Connections',
        'Security',
      ]);
      expect(query(page, '[data-testid="sheet-user"]').textContent).toBe('Ada');
    });

    it('holds the invitations for administrators only', async () => {
      const { page } = await setup({ ...ADA, is_staff: true });

      expect(sheet(page).textContent).toContain('Invitations');
    });

    it('closes with the button', async () => {
      const { fixture, page } = await setup();
      more(page).click();
      await flush(fixture);

      query<HTMLButtonElement>(page, '[data-testid="sheet-close"]').click();
      await flush(fixture);

      expect(sheet(page).open).toBe(false);
      expect(more(page).getAttribute('aria-expanded')).toBe('false');
    });

    it('closes when the dialog closes by itself, as on Escape', async () => {
      const { fixture, page } = await setup();
      more(page).click();
      await flush(fixture);

      sheet(page).close();
      await flush(fixture);

      expect(more(page).getAttribute('aria-expanded')).toBe('false');
    });

    it('closes on a click on the backdrop, not on a click inside', async () => {
      const { fixture, page } = await setup();
      more(page).click();
      await flush(fixture);

      query(page, '[data-testid="sheet"] h2').click();
      await flush(fixture);
      expect(sheet(page).open).toBe(true);

      sheet(page).click();
      await flush(fixture);
      expect(sheet(page).open).toBe(false);
    });

    it('closes when a link is followed', async () => {
      const { fixture, page } = await setup();
      more(page).click();
      await flush(fixture);

      query<HTMLAnchorElement>(page, '[data-testid="sheet"] a').click();
      await flush(fixture);

      expect(sheet(page).open).toBe(false);
    });

    it('signs out from the sheet', async () => {
      const { store, navigate, fixture, page } = await setup();
      more(page).click();
      await flush(fixture);

      query<HTMLButtonElement>(page, '[data-testid="sheet-sign-out"]').click();
      await flush(fixture);

      expect(sheet(page).open).toBe(false);
      expect(store.logout).toHaveBeenCalledTimes(1);
      expect(navigate).toHaveBeenCalledWith('/login');
    });

    it('can be opened again after it was closed', async () => {
      const { fixture, page } = await setup();
      more(page).click();
      await flush(fixture);
      sheet(page).close();
      await flush(fixture);

      more(page).click();
      await flush(fixture);

      expect(sheet(page).open).toBe(true);
      expect(more(page).getAttribute('aria-expanded')).toBe('true');
    });
  });

  describe('theme shortcut', () => {
    afterEach(() => {
      localStorage.clear();
      document.documentElement.removeAttribute('data-theme');
      vi.unstubAllGlobals();
    });

    it('switches the theme from the sidebar, and says what it will do', async () => {
      localStorage.clear();
      const { fixture, page } = await setup();
      const button = () => query<HTMLButtonElement>(page, '[data-testid="theme-toggle"]');
      expect(button().getAttribute('aria-label')).toBe('Switch to the dark theme');

      button().click();
      await fixture.whenStable();

      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
      expect(button().getAttribute('aria-label')).toBe('Switch to the light theme');
    });

    it('switches it from the sheet too, to the same choice', async () => {
      localStorage.clear();
      const { fixture, page } = await setup();

      query<HTMLButtonElement>(page, '[data-testid="sheet-theme-toggle"]').click();
      await fixture.whenStable();

      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
      expect(query(page, '[data-testid="theme-toggle"]').getAttribute('aria-label')).toBe(
        'Switch to the light theme',
      );
    });

    it('shows a moon while the theme is light and a sun while it is dark', async () => {
      localStorage.clear();
      const { fixture, page } = await setup();
      const icon = () => query(page, '[data-testid="theme-toggle"] app-icon svg').innerHTML;
      const light = icon();

      query<HTMLButtonElement>(page, '[data-testid="theme-toggle"]').click();
      await fixture.whenStable();

      expect(icon()).not.toBe(light);
    });
  });
});
