import { Component, DOCUMENT, inject, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { ApiError } from '../../core/auth/auth-models';
import { readInvitationLink } from './invitation-link';
import { passwordsMatch } from './password-match';

const INVITATION_MESSAGE =
  'This invitation is invalid, has expired or was issued for a different email address.';
const CLOSED_MESSAGE = 'Registration is closed on this server.';
const RATE_LIMIT_MESSAGE = 'Too many attempts. Please wait a minute and try again.';
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Account creation for people who follow an invitation link
 * (`/account/signup#invitation=<token>&email=<address>`), or an older query link. The address is shown
 * read-only; the server still checks that the invitation belongs to it.
 */
@Component({
  selector: 'app-signup-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './signup-page.html',
})
export class SignupPage implements OnInit {
  private readonly api = inject(AuthApi);
  private readonly router = inject(Router);
  private readonly invitation = readInvitationLink(inject(DOCUMENT).location.href);

  protected readonly invitationToken = this.invitation.invitationToken;
  protected readonly lockedEmail = this.invitation.email;

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

  ngOnInit(): void {
    void this.router.navigateByUrl('/account/signup', { replaceUrl: true });
  }

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
