import { Component, inject, input, linkedSignal, output, signal } from '@angular/core';
import { ActivitiesApi } from '../../core/activities/activities-api';
import { RatingField } from '../../core/activities/activities-models';
import { ReviewActivity } from '../../core/review/review-models';
import { NOTES_MAX, RPE_CHOICES } from '../activities/manual-activity-format';

const FALLBACK = 'Something went wrong. Please try again.';
const NOTES_TOO_LONG = `Use at most ${NOTES_MAX} characters.`;

/**
 * How hard one session felt (RPE 1 to 10) and a note about it. What is checked here is what the
 * server checks too, so that the message stands next to the field; the server's own messages are
 * shown the same way. The entries stay in the form after a refusal. When the session was saved
 * or is gone, the page is told so that it can fetch the week again: the load follows the rating.
 */
@Component({
  selector: 'app-session-rating',
  templateUrl: './session-rating.html',
  styleUrl: './session-rating.css',
})
export class SessionRating {
  private readonly api = inject(ActivitiesApi);

  readonly activity = input.required<ReviewActivity>();
  /** Another action of the page is running: nothing may start. */
  readonly disabled = input(false);
  /** The rating was stored. */
  readonly rated = output<void>();
  /** The session does not exist any more. */
  readonly gone = output<void>();
  readonly signedOut = output<void>();

  protected readonly ratings = RPE_CHOICES;
  protected readonly notesMax = NOTES_MAX;

  // What the form shows follows what is stored, until the user types.
  protected readonly rpe = linkedSignal(() => String(this.activity().rpe ?? ''));
  protected readonly notes = linkedSignal(() => this.activity().notes);

  protected readonly errors = signal<Partial<Record<RatingField, string>>>({});
  protected readonly message = signal<string | null>(null);
  protected readonly saving = signal(false);

  protected value(event: Event): string {
    return (event.target as HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected async submit(): Promise<void> {
    if (this.saving() || this.disabled()) {
      return;
    }
    this.message.set(null);
    if (this.notes().length > NOTES_MAX) {
      this.errors.set({ notes: NOTES_TOO_LONG });
      return;
    }
    this.errors.set({});

    this.saving.set(true);
    try {
      const result = await this.api.rate(this.activity().id, {
        rpe: this.rpe() === '' ? null : Number(this.rpe()),
        notes: this.notes().trim(),
      });
      switch (result.kind) {
        case 'ok':
          this.rated.emit();
          break;
        case 'invalid':
          this.errors.set(firstMessages(result.errors));
          this.message.set(result.message);
          break;
        case 'not_found':
          this.gone.emit();
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.message.set(FALLBACK);
    } finally {
      this.saving.set(false);
    }
  }
}

function firstMessages(
  errors: Partial<Record<RatingField, string[]>>,
): Partial<Record<RatingField, string>> {
  const first: Partial<Record<RatingField, string>> = {};
  for (const [field, messages] of Object.entries(errors) as [RatingField, string[]][]) {
    first[field] = messages[0];
  }
  return first;
}
