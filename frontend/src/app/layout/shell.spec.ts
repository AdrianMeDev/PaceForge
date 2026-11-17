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
    Array.from(page.querySelectorAll<HTMLElement>('nav [data-group]')).map((group) => [
      group.getAttribute('data-group'),
      Array.from(group.querySelectorAll<HTMLAnchorElement>('a')).map((a) => [
        (a.textContent ?? '').trim(),
        a.getAttribute('href'),
      ]),
    ]);

  const current = (page: HTMLElement) =>
    Array.from(page.querySelectorAll('nav a[aria-current="page"]')).map((a) =>
      (a.textContent ?? '').trim(),
    );

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

      expect(page.querySelector('nav')?.getAttribute('aria-label')).toBe('Main');
      expect(groups(page)).toEqual(MEMBER);
    });

    it('names every group with a heading', async () => {
      const { page } = await setup();

      expect(Array.from(page.querySelectorAll('nav h2')).map((h) => h.textContent?.trim())).toEqual(
        ['Training', 'Planning', 'Settings'],
      );
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

      const links = Array.from(page.querySelectorAll<HTMLAnchorElement>('nav a'));
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

      expect(query(page, 'nav a').classList.contains('active')).toBe(false);
    });
  });
});
