import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';
import { AuthStore } from './auth-store';

/**
 * Both guards read the store synchronously: the app initializer (`app.config.ts`) holds back
 * bootstrapping until the session is known, so a reload never flashes the login page.
 */

/** Routes that need a signed-in user; anonymous visitors are sent to the login with a way back. */
export const authGuard: CanActivateFn = (_route, state) => {
  const router = inject(Router);
  return inject(AuthStore).isAuthenticated()
    ? true
    : router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** Routes for visitors only (login); signed-in users go to the start page instead. */
export const guestGuard: CanActivateFn = () => {
  const router = inject(Router);
  return inject(AuthStore).isAuthenticated() ? router.createUrlTree(['/']) : true;
};

/**
 * The code step of the sign-in only makes sense while the server waits for a second factor;
 * a direct visit goes back to the password step and keeps the return target.
 */
export const mfaPendingGuard: CanActivateFn = (route) => {
  const router = inject(Router);
  return inject(AuthStore)
    .pendingFlows()
    .some((flow) => flow.id === 'mfa_authenticate')
    ? true
    : router.createUrlTree(['/login'], { queryParams: route.queryParams });
};

const SECURITY_PAGE = '/settings/security';

/**
 * An administrator who has not turned on two-factor authentication may only see the security
 * page (and sign out): the admin API refuses them anyway, this sends them to the fix instead of
 * to error messages. Everybody else is not affected.
 */
export const mfaSetupGuard: CanActivateChildFn = (_route, state) => {
  const router = inject(Router);
  if (!inject(AuthStore).user()?.mfa_setup_required) {
    return true;
  }
  return state.url.split(/[?#]/)[0] === SECURITY_PAGE
    ? true
    : router.createUrlTree([SECURITY_PAGE], { queryParams: { notice: 'mfa-required' } });
};
