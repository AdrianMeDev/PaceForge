import { formatDate } from '@angular/common';
import { Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthApi } from '../../core/auth/auth-api';
import { RecoveryCodeSet } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { ActivatedRoute } from '@angular/router';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { PageHeader } from '../../shared/page-header';
import { QrCode } from '../../shared/qr-code';

type View = 'loading' | 'unreachable' | 'off' | 'setup' | 'on' | 'codes';

/** Something the server only does after the password was confirmed again. */
type Action =
  | { kind: 'activate'; code: string }
  | { kind: 'show-codes'; fresh: boolean }
  | { kind: 'regenerate' }
  | { kind: 'deactivate' };

type Confirmation = 'regenerate' | 'deactivate';

const WRONG_CODE =
  'That code is not correct. Check the code in your authenticator app and try again.';
const WRONG_PASSWORD = 'That password is not correct.';
const RATE_LIMIT = 'Too many attempts. Please wait a minute and try again.';
const FALLBACK = 'Something went wrong. Please try again.';

/** Notices other pages may ask for with `?notice=<key>`; any other value is ignored. */
const NOTICES: Record<string, string> = {
  'mfa-required': 'Administrators must turn on two-factor authentication before continuing.',
};

function noticeFor(key: string | null): string | null {
  return key !== null && Object.hasOwn(NOTICES, key) ? NOTICES[key] : null;
}

/**
 * Where users turn their second factor on, check it, replace the recovery codes and turn it
 * off. Setting it up, replacing codes, showing codes and turning it off need the password
 * again; the page then asks for it and repeats what the user wanted.
 */
@Component({
  selector: 'app-security-page',
  imports: [ReactiveFormsModule, ConfirmDialog, PageHeader, QrCode],
  templateUrl: './security-page.html',
  styleUrl: './security-page.css',
})
export class SecurityPage implements OnInit {
  private readonly api = inject(AuthApi);
  private readonly store = inject(AuthStore);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly route = inject(ActivatedRoute);

  protected readonly codeForm = this.fb.group({
    code: ['', [Validators.required, Validators.pattern(/\S/)]],
  });
  protected readonly passwordForm = this.fb.group({ password: ['', Validators.required] });

  protected readonly view = signal<View>('loading');
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(
    noticeFor(this.route.snapshot.queryParamMap.get('notice')),
  );
  protected readonly codeError = signal<string | null>(null);
  protected readonly passwordError = signal<string | null>(null);

  protected readonly setupInfo = signal<{ secret: string; totpUrl: string } | null>(null);
  protected readonly since = signal<number | null>(null);
  protected readonly lastUsed = signal<number | null>(null);
  protected readonly codes = signal<RecoveryCodeSet | null>(null);
  /** Codes that were just created: the user has to save them now. */
  protected readonly freshCodes = signal(false);
  protected readonly confirming = signal<Confirmation | null>(null);
  private readonly confirmDialog = viewChild(ConfirmDialog);
  /** The action waiting for the password. */
  protected readonly reauthFor = signal<Action | null>(null);

  protected readonly isStaff = this.store.isStaff;
  /** " since Nov 12, 2026. Last used Nov 13, 2026, 5:00:00 PM." (built here to control spaces). */
  protected readonly statusDetail = computed(() => {
    const since = this.since();
    const used = this.lastUsed();
    return [
      since === null ? '.' : ` since ${formatDate(since, 'mediumDate', 'en-US')}.`,
      used === null ? '' : ` Last used ${formatDate(used, 'medium', 'en-US')}.`,
    ].join('');
  });
  protected readonly formattedSecret = computed(
    () =>
      this.setupInfo()
        ?.secret.match(/.{1,4}/g)
        ?.join(' ') ?? '',
  );

  ngOnInit(): void {
    void this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    this.errors.set([]);
    if (this.store.user()?.mfa_enabled) {
      await this.showStatus();
    } else {
      this.view.set('off');
    }
  }

  /** Reading the setup data makes the server pick a new secret, so only do it on request. */
  protected async startSetup(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    this.notice.set(null);
    try {
      const status = await this.api.getTotp();
      if (status.kind === 'inactive') {
        this.setupInfo.set({ secret: status.secret, totpUrl: status.totpUrl });
        this.codeForm.reset();
        this.codeError.set(null);
        this.view.set('setup');
      } else {
        this.showActive(status.createdAt, status.lastUsedAt);
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected cancelSetup(): void {
    this.setupInfo.set(null);
    this.errors.set([]);
    this.view.set('off');
  }

  protected async submitCode(): Promise<void> {
    this.codeError.set(null);
    // Codes are often copied with a space in the middle ("123 456").
    const code = this.codeForm.controls.code.value.replace(/\s+/g, '');
    if (!code) {
      this.codeForm.markAllAsTouched();
      return;
    }
    await this.run({ kind: 'activate', code });
  }

  protected showCodes(): Promise<void> {
    return this.run({ kind: 'show-codes', fresh: false });
  }

  protected ask(confirmation: Confirmation): void {
    this.errors.set([]);
    this.confirming.set(confirmation);
    this.confirmDialog()?.open();
  }

  protected async confirmAction(): Promise<void> {
    const confirmation = this.confirming();
    if (confirmation) {
      await this.run({ kind: confirmation });
    }
  }

  protected async submitPassword(): Promise<void> {
    const action = this.reauthFor();
    if (!action || this.busy()) {
      return;
    }
    this.passwordError.set(null);
    const { password } = this.passwordForm.getRawValue();
    if (!password) {
      this.passwordForm.markAllAsTouched();
      return;
    }

    this.busy.set(true);
    try {
      const result = await this.api.reauthenticate(password);
      switch (result.kind) {
        case 'confirmed':
          this.reauthFor.set(null);
          this.passwordForm.reset();
          await this.perform(action);
          break;
        case 'invalid':
          this.passwordError.set(WRONG_PASSWORD);
          break;
        case 'rate_limited':
          this.passwordError.set(RATE_LIMIT);
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected cancelPassword(): void {
    this.reauthFor.set(null);
    this.passwordError.set(null);
    this.passwordForm.reset();
  }

  /** Leaves the list of recovery codes for the status page. */
  protected async doneWithCodes(): Promise<void> {
    this.freshCodes.set(false);
    this.codes.set(null);
    await this.showStatus();
  }

  private async run(action: Action): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      await this.perform(action);
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  private async perform(action: Action): Promise<void> {
    switch (action.kind) {
      case 'activate': {
        const result = await this.api.activateTotp(action.code);
        if (result.kind === 'reauthentication_required') {
          return this.askForPassword(action);
        }
        if (result.kind === 'invalid') {
          this.codeError.set(WRONG_CODE);
          return;
        }
        await this.store.reloadUser();
        return this.perform({ kind: 'show-codes', fresh: true });
      }
      case 'show-codes': {
        const result = await this.api.getRecoveryCodes();
        if (result.kind === 'reauthentication_required') {
          return this.askForPassword(action);
        }
        this.codes.set(result.kind === 'codes' ? result : null);
        this.freshCodes.set(action.fresh);
        this.view.set('codes');
        return;
      }
      case 'regenerate': {
        const result = await this.api.regenerateRecoveryCodes();
        if (result.kind === 'reauthentication_required') {
          return this.askForPassword(action);
        }
        this.confirming.set(null);
        this.codes.set(result);
        this.freshCodes.set(true);
        this.view.set('codes');
        return;
      }
      case 'deactivate': {
        const result = await this.api.deactivateTotp();
        if (result.kind === 'reauthentication_required') {
          return this.askForPassword(action);
        }
        await this.store.reloadUser();
        this.confirming.set(null);
        this.notice.set('Two-factor authentication is turned off.');
        this.view.set('off');
        return;
      }
    }
  }

  private askForPassword(action: Action): void {
    this.passwordForm.reset();
    this.passwordError.set(null);
    this.reauthFor.set(action);
  }

  private async showStatus(): Promise<void> {
    try {
      const status = await this.api.getTotp();
      if (status.kind === 'active') {
        this.showActive(status.createdAt, status.lastUsedAt);
      } else {
        this.view.set('off');
      }
    } catch {
      this.view.set('unreachable');
    }
  }

  private showActive(createdAt: number, lastUsedAt: number | null): void {
    this.since.set(createdAt * 1000);
    this.lastUsed.set(lastUsedAt === null ? null : lastUsedAt * 1000);
    this.view.set('on');
  }
}
