import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { AuthStore } from '../../core/auth/auth-store';

type View = 'checking' | 'ready' | 'confirmed' | 'invalid' | 'unreachable';

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Landing page of the link in the verification email (`/account/verify-email/:key`).
 * Opening the link only looks up which address it is for; the address is confirmed when the
 * visitor presses the button, so mail scanners that fetch links cannot confirm anything.
 */
@Component({
  selector: 'app-verify-email-page',
  imports: [RouterLink],
  templateUrl: './verify-email-page.html',
  styleUrl: './auth-form.css',
})
export class VerifyEmailPage implements OnInit {
  private readonly api = inject(AuthApi);
  private readonly store = inject(AuthStore);
  /** The router has already decoded the path parameter. */
  private readonly key = inject(ActivatedRoute).snapshot.paramMap.get('key') ?? '';

  protected readonly view = signal<View>('checking');
  protected readonly email = signal('');
  protected readonly confirming = signal(false);
  protected readonly error = signal<string | null>(null);
  private readonly signedIn = signal(false);

  /** Where to go after the address is confirmed. */
  protected readonly continueLink = computed(() => (this.signedIn() ? '/' : '/login'));

  ngOnInit(): void {
    void this.check();
  }

  protected async check(): Promise<void> {
    this.view.set('checking');
    this.error.set(null);
    try {
      const info = await this.api.getEmailVerification(this.key);
      if (info.kind === 'valid') {
        this.email.set(info.email);
        this.view.set('ready');
      } else {
        this.view.set('invalid');
      }
    } catch {
      this.view.set('unreachable');
    }
  }

  protected async confirm(): Promise<void> {
    if (this.confirming()) {
      return;
    }
    this.confirming.set(true);
    this.error.set(null);
    try {
      const result = await this.store.verifyEmail(this.key);
      if (result.kind === 'invalid') {
        this.view.set('invalid');
      } else {
        this.signedIn.set(result.kind === 'authenticated' || this.store.isAuthenticated());
        this.view.set('confirmed');
      }
    } catch {
      this.error.set(FALLBACK_MESSAGE);
    } finally {
      this.confirming.set(false);
    }
  }
}
