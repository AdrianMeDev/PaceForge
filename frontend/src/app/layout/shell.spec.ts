import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';
import { ADA, createAuthStoreStub } from '../core/auth/testing/auth-store-stub';
import { Shell } from './shell';
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
          { path: '', pathMatch: 'full', component: Blank },
          { path: 'settings/security', component: Blank },
          { path: 'settings/connections', component: Blank },
          { path: 'admin/invitations', component: Blank },
        ]),
        { provide: AuthStore, useValue: store },
      ],
    });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Shell);
    await fixture.whenStable();
    return { store, navigate, fixture, page: fixture.nativeElement as HTMLElement };
  }

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

    query<HTMLButtonElement>(page, 'button').click();
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();

    expect(store.logout).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  describe('navigation', () => {
    const links = (page: HTMLElement) =>
      Array.from(page.querySelectorAll<HTMLAnchorElement>('nav a')).map((a) => [
        (a.textContent ?? '').trim(),
        a.getAttribute('href'),
      ]);

    it('links to the dashboard, the security page and the connections page', async () => {
      const { page } = await setup();

      expect(links(page)).toEqual([
        ['Dashboard', '/'],
        ['Security', '/settings/security'],
        ['Connections', '/settings/connections'],
      ]);
      expect(page.querySelector('nav')?.getAttribute('aria-label')).toBe('Main');
    });

    it('shows the invitations link to administrators, last', async () => {
      const { page } = await setup({ ...ADA, is_staff: true, mfa_enabled: true });

      expect(links(page)).toEqual([
        ['Dashboard', '/'],
        ['Security', '/settings/security'],
        ['Connections', '/settings/connections'],
        ['Invitations', '/admin/invitations'],
      ]);
    });

    it('does not show the invitations link to members', async () => {
      const { page } = await setup({ ...ADA, mfa_enabled: true });

      expect(links(page).map(([label]) => label)).not.toContain('Invitations');
    });

    it('shows the invitations link to an administrator who still has to set up two-factor', async () => {
      const { page } = await setup({ ...ADA, is_staff: true, mfa_setup_required: true });

      expect(links(page).map(([label]) => label)).toContain('Invitations');
    });

    it('marks the invitations link while that page is open', async () => {
      const { fixture, page, navigate } = await setup({ ...ADA, is_staff: true });
      navigate.mockRestore(); // these tests need real navigation

      await TestBed.inject(Router).navigateByUrl('/admin/invitations');
      await fixture.whenStable();

      const current = Array.from(page.querySelectorAll('nav a[aria-current="page"]')).map((a) =>
        (a.textContent ?? '').trim(),
      );
      expect(current).toEqual(['Invitations']);
    });

    it('shows the connections link to an administrator who still has to set up two-factor', async () => {
      const { page } = await setup({ ...ADA, is_staff: true, mfa_setup_required: true });

      expect(links(page).map(([label]) => label)).toContain('Connections');
    });

    it('marks the connections link while that page is open and nothing else', async () => {
      const { fixture, page, navigate } = await setup();
      navigate.mockRestore(); // these tests need real navigation

      await TestBed.inject(Router).navigateByUrl('/settings/connections');
      await fixture.whenStable();

      const current = Array.from(page.querySelectorAll('nav a[aria-current="page"]')).map((a) =>
        (a.textContent ?? '').trim(),
      );
      expect(current).toEqual(['Connections']);
    });

    it('marks the page that is open', async () => {
      const { fixture, page, navigate } = await setup();
      navigate.mockRestore(); // these tests need real navigation

      await TestBed.inject(Router).navigateByUrl('/settings/security');
      await fixture.whenStable();

      const current = Array.from(page.querySelectorAll('nav a[aria-current="page"]')).map((a) =>
        (a.textContent ?? '').trim(),
      );
      expect(current).toEqual(['Security']);
    });

    it('does not mark the dashboard while another page is open', async () => {
      const { fixture, page, navigate } = await setup();
      navigate.mockRestore(); // these tests need real navigation

      await TestBed.inject(Router).navigateByUrl('/settings/security');
      await fixture.whenStable();

      expect(query(page, 'nav a').classList.contains('active')).toBe(false);
    });
  });
});
