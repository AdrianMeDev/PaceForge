import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { IntervalsConnectionApi } from '../../core/integrations/intervals-api';
import { IntervalsConnection } from '../../core/integrations/intervals-models';
import { AiProviderPanel } from './ai-provider-panel';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const FALLBACK = 'Something went wrong. Please try again.';
const RATE_LIMIT = 'Too many attempts. Please wait a minute and try again.';

/**
 * Where users connect their Intervals.icu account with a personal API key. The key is write-only:
 * it leaves the input field before the request is sent, the field is empty after every attempt
 * (success or not), and the page never shows a key, not even in part.
 */
@Component({
  selector: 'app-connections-page',
  imports: [ReactiveFormsModule, RouterLink, DatePipe, AiProviderPanel],
  templateUrl: './connections-page.html',
  styleUrls: ['../auth/auth-form.css', './connections-page.css'],
})
export class ConnectionsPage implements OnInit {
  private readonly api = inject(IntervalsConnectionApi);

  protected readonly form = inject(NonNullableFormBuilder).group({
    apiKey: ['', [Validators.required, Validators.pattern(/\S/)]],
  });

  protected readonly view = signal<View>('loading');
  protected readonly connection = signal<IntervalsConnection | null>(null);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly confirmingRemoval = signal(false);

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.get();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.connection.set(result.kind === 'connected' ? result.connection : null);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected async connect(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const key = this.form.getRawValue().apiKey.trim();
    this.form.reset(); // the key leaves the page before anything is sent

    this.busy.set(true);
    try {
      const result = await this.api.connect(key);
      switch (result.kind) {
        case 'connected':
          this.connection.set(result.connection);
          this.notice.set(`Connected to Intervals.icu (athlete ${result.connection.athlete_id}).`);
          break;
        case 'invalid_key':
          this.errors.set(result.errors);
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT]);
          break;
        case 'unavailable':
          this.errors.set([result.message]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async check(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.check();
      switch (result.kind) {
        case 'checked':
          this.connection.set(result.connection);
          if (result.connection.status === 'connected') {
            this.notice.set('The key works.');
          } else {
            this.errors.set([
              'Intervals.icu does not accept the stored key any more. Enter a new key below.',
            ]);
          }
          break;
        case 'not_connected':
          this.connection.set(null);
          this.errors.set(['There is no connection any more.']);
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT]);
          break;
        case 'unavailable':
          this.errors.set([result.message]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** The AI provider panel found the session gone. */
  protected endSession(): void {
    this.view.set('signed_out');
  }

  protected askRemoval(): void {
    this.clearMessages();
    this.confirmingRemoval.set(true);
  }

  protected cancelRemoval(): void {
    this.confirmingRemoval.set(false);
  }

  protected async remove(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.disconnect();
      this.confirmingRemoval.set(false);
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.connection.set(null);
      this.notice.set('The connection was removed and the stored key deleted.');
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
