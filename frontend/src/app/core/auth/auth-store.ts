import { Injectable, computed, inject, signal } from '@angular/core';
import { AuthApi } from './auth-api';
import { AuthFlow, AuthStatus, LoginOutcome, Me, VerifyEmailResult } from './auth-models';

/** Single source of truth for "who is logged in", exposed as read-only signals. */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly api = inject(AuthApi);

  private readonly _status = signal<AuthStatus>('loading');
  private readonly _user = signal<Me | null>(null);
  private readonly _pendingFlows = signal<AuthFlow[]>([]);

  readonly status = this._status.asReadonly();
  readonly user = this._user.asReadonly();
  /** Flows still open after a login attempt, e.g. `verify_email`. */
  readonly pendingFlows = this._pendingFlows.asReadonly();
  readonly isAuthenticated = computed(() => this._status() === 'authenticated');
  readonly isStaff = computed(() => this._user()?.is_staff ?? false);

  /**
   * Runs before the app starts: fetches the CSRF cookie and restores an existing session.
   * Never rejects, so a down backend cannot prevent the app from rendering.
   */
  async initialize(): Promise<void> {
    try {
      await this.api.loadConfig();
      const session = await this.api.getSession();
      if (session.kind === 'authenticated') {
        await this.loadUser();
      } else {
        this.setAnonymous(session.flows);
      }
    } catch {
      this._user.set(null);
      this._status.set('unavailable');
    }
  }

  async login(email: string, password: string): Promise<LoginOutcome> {
    const result = await this.api.login(email, password);
    switch (result.kind) {
      case 'authenticated':
        await this.loadUser();
        return { kind: 'success' };
      case 'pending':
        this.setAnonymous(result.flows);
        return result;
      case 'invalid':
        return result;
    }
  }

  /** Confirms an email address; if the server also signed the user in, the user is loaded. */
  async verifyEmail(key: string): Promise<VerifyEmailResult> {
    const result = await this.api.verifyEmail(key);
    if (result.kind === 'authenticated') {
      await this.loadUser();
    }
    return result;
  }

  async logout(): Promise<void> {
    await this.api.logout();
    this.setAnonymous([]);
  }

  private async loadUser(): Promise<void> {
    this._user.set(await this.api.getMe());
    this._pendingFlows.set([]);
    this._status.set('authenticated');
  }

  private setAnonymous(flows: AuthFlow[]): void {
    this._user.set(null);
    this._pendingFlows.set(flows.filter((flow) => flow.is_pending));
    this._status.set('anonymous');
  }
}
