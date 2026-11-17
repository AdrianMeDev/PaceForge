import { Component, OnInit, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { passwordsMatch } from './password-match';

type View = 'checking' | 'form' | 'invalid' | 'unreachable';

const RATE_LIMIT_MESSAGE = 'Too many attempts. Please wait a minute and try again.';
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Landing page of the link in the password reset email (`/account/password/reset/key/:key`).
 * The link is checked first so that nobody types a new password into a dead link.
 */
@Component({
  selector: 'app-password-reset-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './password-reset-page.html',
})
export class PasswordResetPage implements OnInit {
  private readonly api = inject(AuthApi);
  private readonly router = inject(Router);
  /** The router has already decoded the path parameter. */
  private readonly key = inject(ActivatedRoute).snapshot.paramMap.get('key') ?? '';

  protected readonly form = inject(NonNullableFormBuilder).group(
    {
      password: ['', Validators.required],
      passwordConfirm: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );

  protected readonly view = signal<View>('checking');
  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly passwordErrors = signal<string[]>([]);

  ngOnInit(): void {
    void this.check();
  }

  protected async check(): Promise<void> {
    this.view.set('checking');
    this.errors.set([]);
    try {
      const result = await this.api.checkPasswordResetKey(this.key);
      switch (result.kind) {
        case 'valid':
          this.view.set('form');
          break;
        case 'invalid':
          this.view.set('invalid');
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT_MESSAGE]);
          this.view.set('unreachable');
          break;
      }
    } catch {
      this.view.set('unreachable');
    }
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
      const { password } = this.form.getRawValue();
      const result = await this.api.resetPassword(this.key, password);
      switch (result.kind) {
        case 'done':
          await this.router.navigate(['/login'], { queryParams: { notice: 'password-reset' } });
          break;
        case 'invalid':
          if (result.errors.some((error) => error.param === 'key')) {
            this.view.set('invalid');
          } else {
            const messages = result.errors.map((error) => error.message);
            this.passwordErrors.set(messages.length ? messages : [FALLBACK_MESSAGE]);
          }
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
