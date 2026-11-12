import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';
import { AuthApi } from './core/auth/auth-api';
import { AuthStore } from './core/auth/auth-store';
import { ADA, createAuthStoreStub } from './core/auth/testing/auth-store-stub';
import { required } from './testing/dom';

describe('app routes', () => {
  let store: ReturnType<typeof createAuthStoreStub>;
  let harness: RouterTestingHarness;
  let router: Router;

  beforeEach(async () => {
    store = createAuthStoreStub();
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: AuthStore, useValue: store },
        // Pages that talk to the API on their own get a link that is never answered.
        {
          provide: AuthApi,
          useValue: {
            getEmailVerification: () => new Promise<never>(() => undefined),
            checkPasswordResetKey: () => new Promise<never>(() => undefined),
          },
        },
      ],
    });
    harness = await RouterTestingHarness.create();
    router = TestBed.inject(Router);
  });

  it('sends anonymous visitors from the start page to the login', async () => {
    await harness.navigateByUrl('/');

    expect(router.url).toBe('/login?returnUrl=%2F');
    expect(harness.routeNativeElement?.textContent).toContain('Sign in to PaceForge');
  });

  it('shows the dashboard inside the shell for signed-in users', async () => {
    store.signIn();

    await harness.navigateByUrl('/');

    expect(router.url).toBe('/');
    const page = required(harness.routeNativeElement, 'the routed element');
    expect(page.textContent).toContain('Dashboard');
    expect(page.querySelector('[data-testid="user-label"]')?.textContent).toBe('Ada');
  });

  it('keeps signed-in users away from the login page', async () => {
    store.signIn();

    await harness.navigateByUrl('/login');

    expect(router.url).toBe('/');
  });

  it('shows the signup page for an invitation link to visitors', async () => {
    await harness.navigateByUrl('/account/signup?invitation=tok&email=ann%40example.com');

    expect(router.url).toMatch(/^\/account\/signup\?/); // not redirected to the login
    const page = required(harness.routeNativeElement, 'the routed element');
    expect(page.textContent).toContain('Create your account');
    expect(page.querySelector<HTMLInputElement>('#email')?.value).toBe('ann@example.com');
  });

  it('keeps signed-in users away from the signup page', async () => {
    store.signIn();

    await harness.navigateByUrl('/account/signup?invitation=tok');

    expect(router.url).toBe('/');
  });

  it.each([false, true])(
    'opens the email verification link for anyone (signed in: %s)',
    async (signedIn) => {
      if (signedIn) {
        store.signIn();
      }

      await harness.navigateByUrl('/account/verify-email/MQ:1xRY3y:abc');

      expect(router.url).toBe('/account/verify-email/MQ:1xRY3y:abc');
      const page = required(harness.routeNativeElement, 'the routed element');
      expect(page.textContent).toContain('Confirm your email address');
    },
  );

  it('shows the password reset request to visitors', async () => {
    await harness.navigateByUrl('/account/password/reset');

    expect(router.url).toBe('/account/password/reset');
    const page = required(harness.routeNativeElement, 'the routed element');
    expect(page.textContent).toContain('Reset your password');
  });

  it('keeps signed-in users away from the password reset request', async () => {
    store.signIn();

    await harness.navigateByUrl('/account/password/reset');

    expect(router.url).toBe('/');
  });

  it.each([false, true])(
    'opens the password reset link for anyone (signed in: %s)',
    async (signedIn) => {
      if (signedIn) {
        store.signIn();
      }

      await harness.navigateByUrl('/account/password/reset/key/abc-123');

      expect(router.url).toBe('/account/password/reset/key/abc-123');
      const page = required(harness.routeNativeElement, 'the routed element');
      expect(page.textContent).toContain('Choose a new password');
    },
  );

  it('sends visitors without a pending second factor from the code step to the login', async () => {
    await harness.navigateByUrl('/login/mfa?returnUrl=%2Ftraining');

    expect(router.url).toBe('/login?returnUrl=%2Ftraining');
  });

  it('shows the code step while a second factor is pending', async () => {
    store.setPendingFlows([{ id: 'mfa_authenticate', is_pending: true }]);

    await harness.navigateByUrl('/login/mfa');

    expect(router.url).toBe('/login/mfa');
    const page = required(harness.routeNativeElement, 'the routed element');
    expect(page.textContent).toContain('Two-factor authentication');
  });

  it('keeps signed-in users away from the code step', async () => {
    store.setPendingFlows([{ id: 'mfa_authenticate', is_pending: true }]);
    store.signIn();

    await harness.navigateByUrl('/login/mfa');

    expect(router.url).toBe('/');
  });

  it('sends visitors from the security page to the login and remembers where they wanted to go', async () => {
    await harness.navigateByUrl('/settings/security');

    expect(router.url).toBe('/login?returnUrl=%2Fsettings%2Fsecurity');
  });

  it('shows the security page inside the shell for signed-in users', async () => {
    store.signIn();

    await harness.navigateByUrl('/settings/security');

    expect(router.url).toBe('/settings/security');
    const page = required(harness.routeNativeElement, 'the routed element');
    expect(page.textContent).toContain('Two-factor authentication');
    expect(page.querySelector('[data-testid="user-label"]')?.textContent).toBe('Ada');
  });

  describe('an administrator without two-factor authentication', () => {
    const ADMIN_OFF = { ...ADA, is_staff: true, mfa_setup_required: true };

    beforeEach(() => store.signIn(ADMIN_OFF));

    it('is sent from the start page to the security page, with the reason', async () => {
      await harness.navigateByUrl('/');

      expect(router.url).toBe('/settings/security?notice=mfa-required');
      const page = required(harness.routeNativeElement, 'the routed element');
      expect(page.textContent).toContain(
        'Administrators must turn on two-factor authentication before continuing.',
      );
    });

    it('can still open the security page', async () => {
      await harness.navigateByUrl('/settings/security');

      expect(router.url).toBe('/settings/security');
    });

    it('is sent there from the sign-in page too', async () => {
      await harness.navigateByUrl('/login');

      expect(router.url).toBe('/settings/security?notice=mfa-required');
    });

    it('is let through once it is turned on', async () => {
      await harness.navigateByUrl('/settings/security');

      store.signIn({ ...ADMIN_OFF, mfa_enabled: true, mfa_setup_required: false });
      await harness.navigateByUrl('/');

      expect(router.url).toBe('/');
    });
  });

  it('does not hold back administrators who have it, or members', async () => {
    store.signIn({ ...ADA, is_staff: true, mfa_enabled: true });
    await harness.navigateByUrl('/');
    expect(router.url).toBe('/');

    store.signIn(ADA);
    await harness.navigateByUrl('/settings/security');
    await harness.navigateByUrl('/');
    expect(router.url).toBe('/');
  });

  it('redirects unknown paths to the start page', async () => {
    store.signIn();

    await harness.navigateByUrl('/does/not/exist');

    expect(router.url).toBe('/');
  });
});
