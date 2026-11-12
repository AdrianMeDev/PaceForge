import { Component, ElementRef, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiError } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { safeReturnUrl } from './login-page';

const MESSAGES: Record<string, string> = {
  incorrect_code:
    'That code is not correct. Check the code in your authenticator app, or use a recovery code.',
  too_many_login_attempts: 'Too many failed attempts. Please wait a few minutes and try again.',
};

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Second step of the sign-in for accounts with two-factor authentication. The password was
 * already accepted; the server now waits for a code from the authenticator app or for one of
 * the recovery codes (both go into the same field).
 */
@Component({
  selector: 'app-login-mfa-page',
  imports: [ReactiveFormsModule],
  templateUrl: './login-mfa-page.html',
  styleUrl: './auth-form.css',
})
export class LoginMfaPage {
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly returnUrl = inject(ActivatedRoute).snapshot.queryParamMap.get('returnUrl');
  private readonly codeInput = viewChild<ElementRef<HTMLInputElement>>('codeInput');

  protected readonly form = inject(NonNullableFormBuilder).group({
    // Whitespace alone is not a code, although `required` would accept it.
    code: ['', [Validators.required, Validators.pattern(/\S/)]],
  });

  protected readonly submitting = signal(false);
  protected readonly errors = signal<string[]>([]);

  constructor() {
    afterNextRender(() => this.codeInput()?.nativeElement.focus());
  }

  protected async submit(): Promise<void> {
    if (this.submitting()) {
      return;
    }
    this.errors.set([]);
    // Codes are often copied with a space in the middle ("123 456").
    const code = this.form.controls.code.value.replace(/\s+/g, '');
    if (!code) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    try {
      const result = await this.store.authenticateMfa(code);
      switch (result.kind) {
        case 'authenticated':
          await this.router.navigateByUrl(safeReturnUrl(this.returnUrl));
          break;
        case 'invalid':
          this.errors.set(
            result.errors.length ? result.errors.map(messageFor) : [FALLBACK_MESSAGE],
          );
          this.retry();
          break;
        case 'expired':
          await this.router.navigate(['/login'], {
            queryParams: this.queryParams('sign-in-expired'),
          });
          break;
      }
    } catch {
      this.errors.set([FALLBACK_MESSAGE]);
    } finally {
      this.submitting.set(false);
    }
  }

  /** Gives up the half-finished sign-in and goes back to the password step. */
  protected async cancel(): Promise<void> {
    if (this.submitting()) {
      return;
    }
    try {
      await this.store.logout();
    } catch {
      // The server may already have dropped the half-finished sign-in; going back is right anyway.
    }
    await this.router.navigate(['/login'], { queryParams: this.queryParams() });
  }

  private retry(): void {
    this.form.reset();
    this.codeInput()?.nativeElement.focus();
  }

  private queryParams(notice?: string): Record<string, string> {
    return {
      ...(this.returnUrl ? { returnUrl: this.returnUrl } : {}),
      ...(notice ? { notice } : {}),
    };
  }
}

function messageFor(error: ApiError): string {
  return MESSAGES[error.code] ?? error.message ?? FALLBACK_MESSAGE;
}
