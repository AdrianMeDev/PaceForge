import { Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthFlow, ApiError } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';

const MESSAGES: Record<string, string> = {
  email_password_mismatch: 'The email address or the password is not correct.',
  too_many_login_attempts: 'Too many failed attempts. Please wait a few minutes and try again.',
};

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/** Notices other pages may ask for with `?notice=<key>`; any other value is ignored. */
const NOTICES: Record<string, string> = {
  'password-reset': 'Your password has been reset. You can sign in with the new password now.',
  'sign-in-expired': 'Your sign-in took too long. Please sign in again.',
  'account-deleted': 'Your account and its data have been deleted.',
};

export function noticeFor(key: string | null): string | null {
  return key !== null && Object.hasOwn(NOTICES, key) ? NOTICES[key] : null;
}

/** Only same-app paths are accepted as return target; anything else falls back to the start page. */
export function safeReturnUrl(value: string | null): string {
  return value !== null && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}

@Component({
  selector: 'app-login-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login-page.html',
})
export class LoginPage {
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(
    noticeFor(this.route.snapshot.queryParamMap.get('notice')),
  );
  protected readonly serverUnavailable = computed(() => this.store.status() === 'unavailable');

  protected async submit(): Promise<void> {
    if (this.submitting()) {
      return;
    }
    this.errors.set([]);
    this.notice.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    try {
      const { email, password } = this.form.getRawValue();
      const outcome = await this.store.login(email, password);
      switch (outcome.kind) {
        case 'success':
          await this.router.navigateByUrl(
            safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl')),
          );
          break;
        case 'invalid':
          this.errors.set(
            outcome.errors.length ? outcome.errors.map(messageFor) : [FALLBACK_MESSAGE],
          );
          break;
        case 'pending':
          if (outcome.flows.some((flow) => flow.id === 'mfa_authenticate')) {
            // The password was right; the code step keeps the return target from the address.
            await this.router.navigate(['/login/mfa'], { queryParamsHandling: 'preserve' });
          } else {
            this.showPending(outcome.flows);
          }
          break;
      }
    } catch {
      this.errors.set([FALLBACK_MESSAGE]);
    } finally {
      this.submitting.set(false);
    }
  }

  private showPending(flows: AuthFlow[]): void {
    if (flows.some((flow) => flow.id === 'verify_email')) {
      this.notice.set('Please verify your email address first. We have sent you a link.');
    } else {
      // A step this page does not know: the account is fine, but the sign-in cannot be completed.
      this.errors.set(['This account needs a sign-in step that is not supported yet.']);
    }
  }
}

function messageFor(error: ApiError): string {
  return MESSAGES[error.code] ?? error.message ?? FALLBACK_MESSAGE;
}
