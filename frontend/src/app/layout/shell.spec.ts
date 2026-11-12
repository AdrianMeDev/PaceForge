import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';
import { ADA, createAuthStoreStub } from '../core/auth/testing/auth-store-stub';
import { Shell } from './shell';
import { query } from '../testing/dom';

describe('Shell', () => {
  async function setup(user = ADA) {
    const store = createAuthStoreStub();
    store.signIn(user);
    TestBed.configureTestingModule({
      imports: [Shell],
      providers: [provideRouter([]), { provide: AuthStore, useValue: store }],
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
});
