import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, output, signal } from '@angular/core';
import { CoachApi } from '../../core/coach/coach-api';
import {
  AiProviderInput,
  AiProviderKind,
  AiProviderState,
  AiStatus,
} from '../../core/coach/coach-models';

type View = 'loading' | 'unreachable' | 'ready';

const FALLBACK = 'Something went wrong. Please try again.';
const RATE_LIMIT = 'Too many checks. Please wait a minute and try again.';
const GONE = 'There is no AI provider set up any more.';
const REFRESH_FAILED = 'The setup could not be refreshed. Please try again.';
const MODEL_MAX = 100;
const KEY_MAX = 500;
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/;
// Visible ASCII only: the key travels in an HTTP header.
const KEY_PATTERN = /^[\x21-\x7e]+$/;
const KEY_TEXT = 'A key has no spaces or special characters and at most 500 characters.';
const MODEL_TEXT = `Use at most ${MODEL_MAX} characters: letters, digits and . _ : / - (starting with a letter or digit).`;

export const PROVIDER_LABELS: Record<AiProviderKind, string> = {
  anthropic: 'Anthropic',
  openai_compatible: 'OpenAI-compatible (OpenAI, Ollama, llama.cpp …)',
};

export const STATUS_TEXT: Record<AiStatus, string> = {
  untested: 'Not checked yet',
  connected: 'Connected',
  invalid: 'The provider did not accept the key at the last check',
  unavailable: 'The provider could not be reached at the last check',
};

/** The names of the fields as the server knows them, for the messages next to them. */
const FIELDS = ['provider', 'model', 'base_url', 'api_key'];

/**
 * Where users connect their own AI provider: Anthropic, or an OpenAI-compatible endpoint from the
 * list the operator allows. The key is write-only: it leaves the input before anything is sent,
 * the field is empty after every attempt and the page never shows a key, not even in part. A
 * stored key is kept while provider and address stay the same, and is never carried to another
 * place. The connection check uses the saved setup.
 */
@Component({
  selector: 'app-ai-provider-panel',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './ai-provider-panel.html',
  styleUrls: ['../auth/auth-form.css', './ai-provider-panel.css'],
})
export class AiProviderPanel implements OnInit {
  private readonly api = inject(CoachApi);

  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly view = signal<View>('loading');
  protected readonly state = signal<AiProviderState | null>(null);

  protected readonly provider = signal<AiProviderKind>('anthropic');
  protected readonly model = signal('');
  protected readonly baseUrl = signal('');
  protected readonly apiKey = signal('');
  protected readonly removeKey = signal(false);

  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly confirmingRemoval = signal(false);

  protected readonly providerLabel = PROVIDER_LABELS;
  protected readonly statusText = STATUS_TEXT;

  /** Anthropic always; the OpenAI-compatible choice only if the operator allows an address. */
  protected readonly providers = computed<AiProviderKind[]>(() => {
    const state = this.state();
    const compatible =
      state !== null &&
      (state.allowed_base_urls.length > 0 || state.provider === 'openai_compatible');
    return compatible ? ['anthropic', 'openai_compatible'] : ['anthropic'];
  });

  /** The allowed addresses, and the saved one if the operator has taken it off the list. */
  protected readonly addresses = computed(() => {
    const state = this.state();
    if (state === null) {
      return [];
    }
    const listed = state.allowed_base_urls.map((address) => ({ address, allowed: true }));
    const saved = state.base_url;
    return saved !== null && !state.allowed_base_urls.includes(saved)
      ? [...listed, { address: saved, allowed: false }]
      : listed;
  });

  /** The stored key stays only while provider and address are the ones it was given for. */
  protected readonly keyKept = computed(() => {
    const state = this.state();
    return (
      state !== null &&
      state.configured &&
      state.has_key &&
      this.provider() === state.provider &&
      (this.provider() === 'anthropic' || this.baseUrl() === state.base_url)
    );
  });

  /** There are entries that are not saved yet (the check uses what is saved). */
  protected readonly unsaved = computed(() => {
    const state = this.state();
    if (state === null || !state.configured) {
      return false;
    }
    return (
      this.provider() !== state.provider ||
      this.model().trim() !== state.model ||
      (this.provider() === 'openai_compatible' && this.baseUrl() !== state.base_url) ||
      this.apiKey() !== '' ||
      this.removeKey()
    );
  });

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.get();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.apply(result.state);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected read(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  protected chooseProvider(value: string): void {
    // The address field already holds the saved or the first allowed address (see `apply`).
    this.provider.set(value as AiProviderKind);
    this.removeKey.set(false);
  }

  protected setRemoveKey(checked: boolean): void {
    this.removeKey.set(checked);
    if (checked) {
      this.apiKey.set('');
    }
  }

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    const input = this.build();
    if (input === null) {
      return;
    }
    // The key leaves the page before anything is sent.
    this.apiKey.set('');
    this.removeKey.set(false);

    this.busy.set(true);
    try {
      const result = await this.api.save(input);
      switch (result.kind) {
        case 'ok':
          this.apply(result.state);
          this.notice.set('Saved. Press "Check connection" to see that it works.');
          break;
        case 'invalid':
          this.showServerMessages(result.fields, result.errors);
          break;
        case 'forbidden':
          this.signedOut.emit();
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
          this.state.set(result.state);
          if (result.check.ok) {
            this.notice.set('The connection works.');
          } else {
            const wait = result.check.retry_after;
            this.errors.set([
              wait !== null && wait > 0
                ? `${result.check.message} Try again in ${wait} seconds.`
                : result.check.message,
            ]);
          }
          break;
        case 'not_configured':
          this.errors.set([GONE]);
          await this.refresh();
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT]);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
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
      const result = await this.api.remove();
      this.confirmingRemoval.set(false);
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.notice.set('The AI provider was removed and the stored key deleted.');
      await this.refresh();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** The request for what is in the form, or `null` (with the messages set) if it is unusable. */
  private build(): AiProviderInput | null {
    const errors: Record<string, string> = {};
    const model = this.model().trim();
    const provider = this.provider();
    const compatible = provider === 'openai_compatible';
    const key = this.apiKey().trim();

    if (model === '') {
      errors['model'] = 'Enter the name of the model.';
    } else if (model.length > MODEL_MAX || !MODEL_PATTERN.test(model)) {
      errors['model'] = MODEL_TEXT;
    }
    if (compatible && this.baseUrl() === '') {
      errors['base_url'] = 'Choose the address of the endpoint.';
    }
    if (key !== '') {
      if (key.length > KEY_MAX || !KEY_PATTERN.test(key)) {
        errors['api_key'] = KEY_TEXT;
      }
    } else if (provider === 'anthropic' && !this.keyKept()) {
      errors['api_key'] = 'Enter your API key.';
    }
    this.fieldErrors.set(errors);
    if (Object.keys(errors).length > 0) {
      return null;
    }

    const input: AiProviderInput = { provider, model };
    if (compatible) {
      input.base_url = this.baseUrl();
    }
    if (key !== '') {
      input.api_key = key;
    } else if (compatible && this.removeKey()) {
      input.api_key = '';
    }
    return input;
  }

  /** Shows the setup as the server has it and starts the form from it. */
  private apply(state: AiProviderState): void {
    this.state.set(state);
    this.provider.set(state.provider ?? 'anthropic');
    this.model.set(state.model);
    this.baseUrl.set(state.base_url ?? state.allowed_base_urls[0] ?? '');
    this.apiKey.set('');
    this.removeKey.set(false);
  }

  /** Fetches the setup again without leaving the page; a failure is shown above the form. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.api.get();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.apply(result.state);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private showServerMessages(fields: Record<string, string[]>, all: string[]): void {
    const placed: Record<string, string> = {};
    const rest: string[] = [];
    for (const [name, texts] of Object.entries(fields)) {
      if (FIELDS.includes(name)) {
        placed[name] = texts.join(' ');
      } else {
        rest.push(...texts);
      }
    }
    this.fieldErrors.set(placed);
    this.errors.set(rest.length > 0 || Object.keys(fields).length > 0 ? rest : all);
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
    this.fieldErrors.set({});
  }
}
