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

    it('links to the dashboard and the security page', async () => {
      const { page } = await setup();

      expect(links(page)).toEqual([
        ['Dashboard', '/'],
        ['Security', '/settings/security'],
      ]);
      expect(page.querySelector('nav')?.getAttribute('aria-label')).toBe('Main');
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
