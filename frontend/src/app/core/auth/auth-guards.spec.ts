import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  CanActivateFn,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';
import { authGuard, guestGuard, mfaPendingGuard } from './auth-guards';
import { AuthStore } from './auth-store';
import { createAuthStoreStub } from './testing/auth-store-stub';

describe('route guards', () => {
  const store = createAuthStoreStub();
  let router: Router;

  function run(guard: CanActivateFn, url = '/dashboard', queryParams: Record<string, string> = {}) {
    return TestBed.runInInjectionContext(() =>
      guard({ queryParams } as unknown as ActivatedRouteSnapshot, { url } as RouterStateSnapshot),
    );
  }

  beforeEach(() => {
    store.setStatus('anonymous');
    store.setPendingFlows([]);
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: AuthStore, useValue: store }],
    });
    router = TestBed.inject(Router);
  });

  describe('authGuard', () => {
    it('lets signed-in users through', () => {
      store.signIn();

      expect(run(authGuard)).toBe(true);
    });

    it('sends anonymous visitors to the login and remembers where they wanted to go', () => {
      const result = run(authGuard, '/training/week?day=2');

      expect(result).toBeInstanceOf(UrlTree);
      expect(router.serializeUrl(result as UrlTree)).toBe(
        '/login?returnUrl=%2Ftraining%2Fweek%3Fday%3D2',
      );
    });

    it('does not let anyone in while the backend is unavailable', () => {
      store.setStatus('unavailable');

      expect(run(authGuard)).toBeInstanceOf(UrlTree);
    });
  });

  describe('guestGuard', () => {
    it('lets anonymous visitors see the login', () => {
      expect(run(guestGuard)).toBe(true);
    });

    it('lets visitors see the login while the backend is unavailable', () => {
      store.setStatus('unavailable');

      expect(run(guestGuard)).toBe(true);
    });

    it('sends signed-in users to the start page', () => {
      store.signIn();

      const result = run(guestGuard);

      expect(router.serializeUrl(result as UrlTree)).toBe('/');
    });
  });

  describe('mfaPendingGuard', () => {
    it('lets visitors in while the server waits for a second factor', () => {
      store.setPendingFlows([{ id: 'mfa_authenticate', is_pending: true }]);

      expect(run(mfaPendingGuard, '/login/mfa')).toBe(true);
    });

    it('sends a direct visit back to the password step and keeps the return target', () => {
      const result = run(mfaPendingGuard, '/login/mfa', { returnUrl: '/training' });

      expect(router.serializeUrl(result as UrlTree)).toBe('/login?returnUrl=%2Ftraining');
    });

    it('does not take other pending steps for a second factor', () => {
      store.setPendingFlows([{ id: 'verify_email', is_pending: true }]);

      expect(run(mfaPendingGuard, '/login/mfa')).toBeInstanceOf(UrlTree);
    });
  });
});
