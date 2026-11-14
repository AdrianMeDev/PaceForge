import { Component, inject, input, linkedSignal, output, signal } from '@angular/core';
import { ReviewApi } from '../../core/review/review-api';
import { FeedbackField, WeekFeedback, WeekReview } from '../../core/review/review-models';
import { NOTES_MAX } from '../activities/manual-activity-format';
import { FEEDBACK_SCALES } from './review-format';

const FALLBACK = 'Something went wrong. Please try again.';
const NOTES_TOO_LONG = `Use at most ${NOTES_MAX} characters.`;

type Scale = 'fatigue' | 'motivation' | 'pain';

/**
 * How the user felt about the week: tiredness, motivation and pain on a scale from 1 to 5, and a
 * note. What is checked here is what the server checks too; its own messages are shown the same
 * way. The entries stay in the form after a refusal. The form replaces the earlier feedback of the
 * week: what is left empty is empty afterwards, and nothing at all removes the feedback. The note
 * is the user's own and is never sent to the coach.
 */
@Component({
  selector: 'app-week-feedback-form',
  templateUrl: './week-feedback-form.html',
  styleUrls: ['../auth/auth-form.css', './week-feedback-form.css'],
})
export class WeekFeedbackForm {
  private readonly api = inject(ReviewApi);

  /** The Monday of the week, YYYY-MM-DD. */
  readonly week = input.required<string>();
  /** What is stored now; `null`: nothing. */
  readonly feedback = input<WeekFeedback | null>(null);
  /** Another action of the page is running: nothing may start. */
  readonly disabled = input(false);
  /** The feedback was stored; the whole week comes back with it. */
  readonly saved = output<WeekReview>();
  /** The week cannot be reviewed any more. */
  readonly notReviewable = output<void>();
  readonly signedOut = output<void>();

  protected readonly scales = FEEDBACK_SCALES;
  protected readonly notesMax = NOTES_MAX;

  // What the form shows follows what is stored, until the user types.
  protected readonly values = linkedSignal<Record<Scale, string>>(() => ({
    fatigue: String(this.feedback()?.fatigue ?? ''),
    motivation: String(this.feedback()?.motivation ?? ''),
    pain: String(this.feedback()?.pain ?? ''),
  }));
  protected readonly notes = linkedSignal(() => this.feedback()?.notes ?? '');

  protected readonly errors = signal<Partial<Record<FeedbackField, string>>>({});
  protected readonly message = signal<string | null>(null);
  protected readonly saving = signal(false);

  protected value(event: Event): string {
    return (event.target as HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected choose(scale: Scale, value: string): void {
    this.values.update((current) => ({ ...current, [scale]: value }));
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
      const values = this.values();
      const result = await this.api.saveFeedback(this.week(), {
        fatigue: asScale(values.fatigue),
        motivation: asScale(values.motivation),
        pain: asScale(values.pain),
        notes: this.notes().trim(),
      });
      switch (result.kind) {
        case 'ok':
          this.saved.emit(result.review);
          break;
        case 'invalid':
          this.errors.set(firstMessages(result.errors));
          this.message.set(result.message);
          break;
        case 'not_reviewable':
          this.notReviewable.emit();
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

function asScale(value: string): number | null {
  return value === '' ? null : Number(value);
}

function firstMessages(
  errors: Partial<Record<FeedbackField, string[]>>,
): Partial<Record<FeedbackField, string>> {
  const first: Partial<Record<FeedbackField, string>> = {};
  for (const [field, messages] of Object.entries(errors) as [FeedbackField, string[]][]) {
    first[field] = messages[0];
  }
  return first;
}
