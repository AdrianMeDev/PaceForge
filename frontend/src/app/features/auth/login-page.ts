import { Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthFlow, ApiError } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';

const MESSAGES: Record<string, string> = {
  email_password_mismatch: 'The email address or the password is not correct.',
  too_many_login_attempts: 'Too many failed attempts. Please wait a few minutes and try again.',
};

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/** Only same-app paths are accepted as return target; anything else falls back to the start page. */
export function safeReturnUrl(value: string | null): string {
  return value !== null && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}

@Component({
  selector: 'app-login-page',
  imports: [ReactiveFormsModule],
  templateUrl: './login-page.html',
  styleUrl: './login-page.css',
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
  protected readonly notice = signal<string | null>(null);
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
          this.showPending(outcome.flows);
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
      // e.g. a second factor: the account is fine, but this page cannot complete the sign-in yet.
      this.errors.set(['This account needs a sign-in step that is not supported yet.']);
    }
  }
}

function messageFor(error: ApiError): string {
  return MESSAGES[error.code] ?? error.message ?? FALLBACK_MESSAGE;
}
