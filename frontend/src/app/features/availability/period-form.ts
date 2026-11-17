import { AfterViewInit, Component, ElementRef, inject, output, signal } from '@angular/core';
import { AvailabilityApi } from '../../core/availability/availability-api';
import { Period, PeriodInput, PeriodKind } from '../../core/availability/availability-models';
import {
  PERIOD_KIND_LABELS,
  PERIOD_MAX_DAYS,
  inclusiveDays,
  isCalendarDate,
} from './availability-format';

const NOTE_MAX = 200;
const FALLBACK = 'Something went wrong. Please try again.';
const DATE_HELP = 'Enter a date like 2027-07-12.';

/** The names of the fields as the form knows them, for the messages next to them. */
const SERVER_FIELDS: Record<string, string> = {
  kind: 'kind',
  start_date: 'start',
  end_date: 'end',
  note: 'note',
};

/**
 * Adds a period of absence. What is checked here is what the server checks too, so that the
 * message appears next to the field without a round trip; the server's own messages are shown the
 * same way. Saving is one request at a time.
 */
@Component({
  selector: 'app-period-form',
  templateUrl: './period-form.html',
  styleUrl: './period-form.css',
})
export class PeriodForm implements AfterViewInit {
  private readonly api = inject(AvailabilityApi);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  /** The period as the server saved it. */
  readonly saved = output<Period>();
  readonly cancelled = output<void>();
  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly kind = signal<PeriodKind>('vacation');
  protected readonly start = signal('');
  protected readonly end = signal('');
  protected readonly note = signal('');
  protected readonly busy = signal(false);
  /** Messages by field; `form` is for everything that concerns the whole period. */
  protected readonly errors = signal<Record<string, string>>({});

  protected readonly kinds = Object.entries(PERIOD_KIND_LABELS);

  ngAfterViewInit(): void {
    // The form opens somewhere above or below the user's eyes; the first day is where to begin.
    this.host.nativeElement.querySelector<HTMLInputElement>('#period-start')?.focus();
  }

  protected read(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  /** Most periods are one day or start where the last one ended: an empty end follows the start. */
  protected setStart(value: string): void {
    this.start.set(value);
    if (this.end() === '') {
      this.end.set(value);
    }
  }

  protected cancel(): void {
    this.cancelled.emit();
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    const input = this.build();
    if (input === null) {
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.api.createPeriod(input);
      switch (result.kind) {
        case 'ok':
          this.saved.emit(result.period);
          break;
        case 'invalid':
          this.errors.set(serverMessages(result.fields, result.errors));
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set({ form: FALLBACK });
    } finally {
      this.busy.set(false);
    }
  }

  /** The request for what is in the form, or `null` (with the messages set) if it is unusable. */
  private build(): PeriodInput | null {
    const errors: Record<string, string> = {};
    const start = this.start();
    const end = this.end();
    if (start === '') {
      errors['start'] = 'Enter the first day.';
    } else if (!isCalendarDate(start)) {
      errors['start'] = DATE_HELP;
    }
    if (end === '') {
      errors['end'] = 'Enter the last day.';
    } else if (!isCalendarDate(end)) {
      errors['end'] = DATE_HELP;
    }
    const days = inclusiveDays(start, end);
    if (days !== null && days < 1) {
      errors['end'] = 'The end cannot be before the start.';
    } else if (days !== null && days > PERIOD_MAX_DAYS) {
      errors['end'] = `A period can last at most ${PERIOD_MAX_DAYS} days.`;
    }
    if (this.note().length > NOTE_MAX) {
      errors['note'] = `Use at most ${NOTE_MAX} characters.`;
    }
    this.errors.set(errors);
    return Object.keys(errors).length === 0
      ? { kind: this.kind(), start_date: start, end_date: end, note: this.note() }
      : null;
  }
}

/** The server's messages by the form's field names; the rest goes to the form as a whole. */
function serverMessages(fields: Record<string, string[]>, all: string[]): Record<string, string> {
  const messages: Record<string, string> = {};
  for (const [name, texts] of Object.entries(fields)) {
    const field = SERVER_FIELDS[name] ?? 'form';
    messages[field] = [messages[field], ...texts].filter(Boolean).join(' ');
  }
  return Object.keys(messages).length ? messages : { form: all.join(' ') };
}
