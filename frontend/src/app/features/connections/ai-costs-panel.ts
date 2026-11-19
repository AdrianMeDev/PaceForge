import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, output, signal, viewChild } from '@angular/core';
import { CoachApi } from '../../core/coach/coach-api';
import { AiCostsState, ModelPrice, MonthlyUsage } from '../../core/coach/coach-models';
import { ConfirmDialog } from '../../shared/confirm-dialog';

type View = 'loading' | 'unreachable' | 'ready';

const FALLBACK = 'Something went wrong. Please try again.';
const REFRESH_FAILED = 'The costs could not be refreshed. Please try again.';
const MODEL_MAX = 100;
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/;
const MODEL_TEXT = `Use at most ${MODEL_MAX} characters: letters, digits and . _ : / - (starting with a letter or digit).`;
// A price is a number from 0 to 999999.9999 with at most four decimal places.
const PRICE_PATTERN = /^\d+(\.\d{1,4})?$/;
const PRICE_MAX = 999999.9999;
const PRICE_TEXT = 'Enter a price from 0 to 999999.9999 with at most four decimal places.';

/** The names of the fields as the server knows them, for the messages next to them. */
const FIELDS = ['model', 'input_per_million', 'output_per_million', 'cached_per_million'];

const MONTH_FORMAT = new Intl.DateTimeFormat('en-US', {
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

/**
 * What the user's own AI calls cost: calls, tokens and an estimated cost in USD per month, and the
 * prices per million tokens that the estimate is made from. Prices are optional. A month with a
 * model that has no price says so, and its cost is then only a lower bound. The server does the
 * sums; this panel only shows them and sends the prices as the user typed them.
 */
@Component({
  selector: 'app-ai-costs-panel',
  imports: [CurrencyPipe, DecimalPipe, ConfirmDialog],
  templateUrl: './ai-costs-panel.html',
  styleUrl: './ai-costs-panel.css',
})
export class AiCostsPanel implements OnInit {
  private readonly api = inject(CoachApi);

  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly view = signal<View>('loading');
  protected readonly costs = signal<AiCostsState | null>(null);

  /** The price being edited; `null`: a new one is being added. */
  protected readonly editing = signal<ModelPrice | null>(null);
  protected readonly model = signal('');
  protected readonly inputPrice = signal('');
  protected readonly outputPrice = signal('');
  protected readonly cachedPrice = signal('');

  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  protected readonly pendingRemoval = signal<ModelPrice | null>(null);
  private readonly removalDialog = viewChild(ConfirmDialog);

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.getCosts();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.costs.set(result.state);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  /** Fetches the figures again without leaving the page (a call has been made meanwhile). */
  async reload(): Promise<void> {
    if (this.view() !== 'ready') {
      return;
    }
    try {
      const result = await this.api.getCosts();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.costs.set(result.state);
    } catch {
      this.errors.update((list) =>
        list.includes(REFRESH_FAILED) ? list : [...list, REFRESH_FAILED],
      );
    }
  }

  protected read(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected monthLabel(month: string): string {
    const [year, number] = month.split('-').map(Number);
    return MONTH_FORMAT.format(new Date(Date.UTC(year, number - 1, 1)));
  }

  /** How the cost of a month is to be read: nothing priced, partly priced, or all priced. */
  protected costKind(month: MonthlyUsage): 'none' | 'partial' | 'full' {
    if (month.cost === null) {
      return 'none';
    }
    return month.unpriced_models.length > 0 ? 'partial' : 'full';
  }

  protected startEdit(price: ModelPrice): void {
    this.clearMessages();
    this.editing.set(price);
    this.model.set(price.model);
    this.inputPrice.set(price.input_per_million);
    this.outputPrice.set(price.output_per_million);
    this.cachedPrice.set(price.cached_per_million ?? '');
  }

  protected cancelEdit(): void {
    this.clearMessages();
    this.resetForm();
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

    this.busy.set(true);
    try {
      const result = await this.api.savePrice(input);
      switch (result.kind) {
        case 'ok':
          this.costs.set(result.state);
          this.notice.set(`The price of ${input.model} was saved.`);
          this.resetForm();
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

  protected askRemoval(price: ModelPrice): void {
    this.clearMessages();
    this.pendingRemoval.set(price);
    this.removalDialog()?.open();
  }

  protected async remove(): Promise<void> {
    const price = this.pendingRemoval();
    if (price === null || this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.deletePrice(price.id);
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      if (this.editing()?.id === price.id) {
        this.resetForm();
      }
      this.notice.set(
        result.kind === 'deleted'
          ? `The price of ${price.model} was removed.`
          : `The price of ${price.model} was already gone.`,
      );
      await this.refreshAfterChange();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.pendingRemoval.set(null);
      this.busy.set(false);
    }
  }

  /** The request for what is in the form, or `null` (with the messages set) if it is unusable. */
  private build() {
    const errors: Record<string, string> = {};
    const model = this.model().trim();
    if (model === '') {
      errors['model'] = 'Enter the name of the model.';
    } else if (model.length > MODEL_MAX || !MODEL_PATTERN.test(model)) {
      errors['model'] = MODEL_TEXT;
    }
    const input = this.parsePrice(this.inputPrice(), 'input_per_million', errors, true);
    const output = this.parsePrice(this.outputPrice(), 'output_per_million', errors, true);
    const cached = this.parsePrice(this.cachedPrice(), 'cached_per_million', errors, false);
    this.fieldErrors.set(errors);
    if (Object.keys(errors).length > 0 || input === null || output === null) {
      return null;
    }
    return {
      model,
      input_per_million: input,
      output_per_million: output,
      cached_per_million: cached,
    };
  }

  private parsePrice(
    raw: string,
    name: string,
    errors: Record<string, string>,
    required: boolean,
  ): number | null {
    const text = raw.trim();
    if (text === '') {
      if (required) {
        errors[name] = 'Enter a price.';
      }
      return null;
    }
    const value = Number(text);
    if (!PRICE_PATTERN.test(text) || !(value <= PRICE_MAX)) {
      errors[name] = PRICE_TEXT;
      return null;
    }
    return value;
  }

  private resetForm(): void {
    this.editing.set(null);
    this.model.set('');
    this.inputPrice.set('');
    this.outputPrice.set('');
    this.cachedPrice.set('');
  }

  /** After a removal the figures are fetched again; a failure is shown above the list. */
  private async refreshAfterChange(): Promise<void> {
    try {
      const result = await this.api.getCosts();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.costs.set(result.state);
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
