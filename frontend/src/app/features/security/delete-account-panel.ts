import { ChangeDetectionStrategy, Component, inject, signal, viewChild } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { ApiError } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { ConfirmDialog } from '../../shared/confirm-dialog';

type Field = 'confirmation' | 'password' | 'mfaCode';

const RATE_LIMIT = 'Too many attempts. Please wait a minute and try again.';
const LAST_ADMIN =
  'You are the only administrator. Make another user an administrator before you delete this account.';
const FORBIDDEN = 'You are signed out. Please sign in again to delete your account.';
const FALLBACK = 'Something went wrong. Please try again.';

/** The server's name for each field of the request. */
const FIELD_OF_PARAM: Record<string, Field> = {
  confirmation: 'confirmation',
  password: 'password',
  mfa_code: 'mfaCode',
};

/**
 * Deletes the account of the signed-in user with all its data. The athlete types the email address
 * again, the password and, with two-factor authentication on, a code; a last question follows
 * before anything is sent. Intervals.icu is never touched.
 */
@Component({
  selector: 'app-delete-account-panel',
  imports: [ReactiveFormsModule, ConfirmDialog],
  templateUrl: './delete-account-panel.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DeleteAccountPanel {
  private readonly api = inject(AuthApi);
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly confirmDialog = viewChild(ConfirmDialog);

  protected readonly form = this.fb.group({
    confirmation: ['', [Validators.required, Validators.pattern(/\S/)]],
    password: ['', Validators.required],
    mfaCode: [''],
  });

  protected readonly user = this.store.user;
  protected readonly busy = signal(false);
  protected readonly alert = signal<string | null>(null);
  protected readonly serverErrors = signal<Partial<Record<Field, string>>>({});
  protected readonly mismatch = signal(false);

  /** The question before the request: validates the form first. */
  protected ask(): void {
    if (this.busy()) {
      return;
    }
    this.alert.set(null);
    this.serverErrors.set({});
    this.mismatch.set(false);
    const needsCode = this.user()?.mfa_enabled === true;
    const { confirmation, mfaCode } = this.form.getRawValue();
    if (needsCode && !mfaCode.trim()) {
      this.form.controls.mfaCode.setErrors({ required: true });
    }
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      return;
    }
    if (confirmation.trim().toLowerCase() !== (this.user()?.email ?? '').toLowerCase()) {
      this.mismatch.set(true);
      return;
    }
    this.confirmDialog()?.open();
  }

  protected async delete(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    const { confirmation, password, mfaCode } = this.form.getRawValue();
    try {
      const result = await this.api.deleteAccount({
        confirmation: confirmation.trim(),
        password,
        mfaCode: this.user()?.mfa_enabled ? mfaCode.replace(/\s+/g, '') : '',
      });
      switch (result.kind) {
        case 'deleted':
          this.form.reset();
          this.store.clearSession();
          await this.router.navigate(['/login'], { queryParams: { notice: 'account-deleted' } });
          break;
        case 'invalid':
          this.showFieldErrors(result.errors);
          break;
        case 'last_admin':
          this.alert.set(LAST_ADMIN);
          break;
        case 'rate_limited':
          this.alert.set(RATE_LIMIT);
          break;
        case 'forbidden':
          this.alert.set(FORBIDDEN);
          break;
      }
    } catch {
      this.alert.set(FALLBACK);
    } finally {
      this.busy.set(false);
    }
  }

  private showFieldErrors(errors: ApiError[]): void {
    const byField: Partial<Record<Field, string>> = {};
    for (const error of errors) {
      const field = FIELD_OF_PARAM[error.param ?? ''];
      if (field !== undefined && byField[field] === undefined) {
        byField[field] = error.message;
      }
    }
    if (Object.keys(byField).length === 0) {
      this.alert.set(FALLBACK);
      return;
    }
    this.serverErrors.set(byField);
  }
}
