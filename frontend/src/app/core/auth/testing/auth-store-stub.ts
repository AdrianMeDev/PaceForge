import { computed, signal } from '@angular/core';
import {
  AuthFlow,
  AuthStatus,
  LoginOutcome,
  Me,
  MfaAuthenticateResult,
  VerifyEmailResult,
} from '../auth-models';

export const ADA: Me = {
  id: '1',
  email: 'ada@example.com',
  display_name: 'Ada',
  is_staff: false,
  mfa_enabled: false,
  mfa_setup_required: false,
};

/** Stand-in for `AuthStore` in component and routing tests; provide it with `useValue`. */
export function createAuthStoreStub(initial: { status?: AuthStatus; user?: Me | null } = {}) {
  const status = signal<AuthStatus>(initial.status ?? 'anonymous');
  const user = signal<Me | null>(initial.user ?? null);
  const pendingFlows = signal<AuthFlow[]>([]);
  return {
    status: status.asReadonly(),
    user: user.asReadonly(),
    pendingFlows: pendingFlows.asReadonly(),
    isAuthenticated: computed(() => status() === 'authenticated'),
    login: vi.fn<(email: string, password: string) => Promise<LoginOutcome>>(),
    logout: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
    verifyEmail: vi.fn<(key: string) => Promise<VerifyEmailResult>>(),
    authenticateMfa: vi.fn<(code: string) => Promise<MfaAuthenticateResult>>(),
    reloadUser: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
    signIn(me: Me = ADA): void {
      user.set(me);
      status.set('authenticated');
    },
    setPendingFlows(flows: AuthFlow[]): void {
      pendingFlows.set(flows);
    },
    setStatus(next: AuthStatus): void {
      status.set(next);
    },
  };
}
