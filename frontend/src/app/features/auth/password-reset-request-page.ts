import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';

const RATE_LIMIT_MESSAGE = 'Too many requests. Please wait a minute and try again.';
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Asks for a password reset link. The server answers the same way for every address, and so
 * does this page: it never says whether an account exists.
 */
@Component({
  selector: 'app-password-reset-request-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './password-reset-request-page.html',
  styleUrl: './auth-form.css',
})
export class PasswordResetRequestPage {
  private readonly api = inject(AuthApi);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });

  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  /** The address a link was requested for, once the request went through. */
  protected readonly requestedFor = signal<string | null>(null);

  protected async submit(): Promise<void> {
    if (this.submitting()) {
      return;
    }
    this.errors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    try {
      const { email } = this.form.getRawValue();
      const result = await this.api.requestPasswordReset(email);
      switch (result.kind) {
        case 'sent':
          this.requestedFor.set(email);
          break;
        case 'invalid':
          this.errors.set(
            result.errors.length ? result.errors.map((e) => e.message) : [FALLBACK_MESSAGE],
          );
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT_MESSAGE]);
          break;
      }
    } catch {
      this.errors.set([FALLBACK_MESSAGE]);
    } finally {
      this.submitting.set(false);
    }
  }
}
