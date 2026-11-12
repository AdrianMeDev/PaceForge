import { Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { ApiError } from '../../core/auth/auth-models';

const INVITATION_MESSAGE =
  'This invitation is invalid, has expired or was issued for a different email address.';
const CLOSED_MESSAGE = 'Registration is closed on this server.';
const RATE_LIMIT_MESSAGE = 'Too many attempts. Please wait a minute and try again.';
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  return group.get('password')?.value === group.get('passwordConfirm')?.value
    ? null
    : { passwordMismatch: true };
}

/**
 * Account creation for people who follow an invitation link
 * (`/account/signup?invitation=<token>&email=<address>`). The address from the link is shown
 * read-only; the server still checks that the invitation belongs to it.
 */
@Component({
  selector: 'app-signup-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './signup-page.html',
  styleUrl: './auth-form.css',
})
export class SignupPage {
  private readonly api = inject(AuthApi);
  private readonly params = inject(ActivatedRoute).snapshot.queryParamMap;

  protected readonly invitationToken = (this.params.get('invitation') ?? '').trim();
  protected readonly lockedEmail = (this.params.get('email') ?? '').trim();

  protected readonly form = inject(NonNullableFormBuilder).group(
    {
      email: [this.lockedEmail, [Validators.required, Validators.email]],
      password: ['', Validators.required],
      passwordConfirm: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );

  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly passwordErrors = signal<string[]>([]);
  protected readonly created = signal<{ email: string; needsVerification: boolean } | null>(null);

  protected async submit(): Promise<void> {
    if (this.submitting()) {
      return;
    }
    this.errors.set([]);
    this.passwordErrors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    try {
      const { email, password } = this.form.getRawValue();
      const result = await this.api.signup({
        email,
        password,
        invitationToken: this.invitationToken,
      });
      switch (result.kind) {
        case 'pending':
          this.created.set({ email, needsVerification: true });
          this.form.reset();
          break;
        case 'authenticated': // only if email verification is switched off on the server
          this.created.set({ email, needsVerification: false });
          this.form.reset();
          break;
        case 'invalid':
          this.showErrors(result.errors);
          break;
        case 'closed':
          this.errors.set([CLOSED_MESSAGE]);
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

  /** Password rule violations belong under the password field, everything else on top. */
  private showErrors(errors: ApiError[]): void {
    const general: string[] = [];
    const password: string[] = [];
    for (const error of errors) {
      if (error.code === 'invalid_invitation') {
        general.push(INVITATION_MESSAGE);
      } else if (error.param === 'password') {
        password.push(error.message);
      } else {
        general.push(error.message || FALLBACK_MESSAGE);
      }
    }
    this.errors.set(general.length || password.length ? general : [FALLBACK_MESSAGE]);
    this.passwordErrors.set(password);
  }
}
