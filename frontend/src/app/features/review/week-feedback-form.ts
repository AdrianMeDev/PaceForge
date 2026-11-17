import { Component, inject, input, linkedSignal, output, signal } from '@angular/core';
import { ReviewApi } from '../../core/review/review-api';
import {
  FeedbackField,
  WeekFeedback,
  WeekReview,
  WeekVerdict,
} from '../../core/review/review-models';
import { NOTES_MAX } from '../activities/manual-activity-format';
import { WEEK_NOTE_MAX } from '../planning/plan-format';
import { FEEDBACK_SCALES, VERDICT_CHOICES } from './review-format';

const FALLBACK = 'Something went wrong. Please try again.';
const NOTES_TOO_LONG = `Use at most ${NOTES_MAX} characters.`;
const NEXT_NOTE_TOO_LONG = `Use at most ${WEEK_NOTE_MAX} characters.`;

type Scale = 'fatigue' | 'motivation' | 'pain';
type Field = FeedbackField | 'nextNote';

/**
 * How the user felt about the week: tiredness, motivation and pain on a scale from 1 to 5, the
 * week as a whole in one word, and a note. What is checked here is what the server checks too; its
 * own messages are shown the same way. The entries stay in the form after a refusal. The form
 * replaces the earlier feedback of the week: what is left empty is empty afterwards, and nothing
 * at all removes the feedback. The note is the user's own and is never sent to the coach.
 *
 * The second button closes the week: it saves the same feedback and, if that worked, hands the
 * week and the user's note for the next week to the page (`closed`), which asks the coach for the
 * draft. The note for the next week is not stored here.
 */
@Component({
  selector: 'app-week-feedback-form',
  templateUrl: './week-feedback-form.html',
  styleUrl: './week-feedback-form.css',
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
  /** The feedback was stored to close the week; `note` is what to tell the coach about the next. */
  readonly closed = output<{ review: WeekReview; note: string }>();
  /** The week cannot be reviewed any more. */
  readonly notReviewable = output<void>();
  readonly signedOut = output<void>();

  protected readonly scales = FEEDBACK_SCALES;
  protected readonly notesMax = NOTES_MAX;
  protected readonly noteMax = WEEK_NOTE_MAX;
  protected readonly verdicts = VERDICT_CHOICES;

  // What the form shows follows what is stored, until the user types.
  protected readonly values = linkedSignal<Record<Scale, string>>(() => ({
    fatigue: String(this.feedback()?.fatigue ?? ''),
    motivation: String(this.feedback()?.motivation ?? ''),
    pain: String(this.feedback()?.pain ?? ''),
  }));
  protected readonly verdict = linkedSignal<string>(() => this.feedback()?.verdict ?? '');
  protected readonly notes = linkedSignal(() => this.feedback()?.notes ?? '');
  /** What to tell the coach about the next week; it stays in the form until the week is closed. */
  protected readonly nextNote = signal('');

  protected readonly errors = signal<Partial<Record<Field, string>>>({});
  protected readonly message = signal<string | null>(null);
  protected readonly saving = signal(false);

  protected value(event: Event): string {
    return (event.target as HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected choose(scale: Scale, value: string): void {
    this.values.update((current) => ({ ...current, [scale]: value }));
  }

  protected async submit(close: boolean): Promise<void> {
    if (this.saving() || this.disabled()) {
      return;
    }
    this.message.set(null);
    const tooLong: Partial<Record<Field, string>> = {};
    if (this.notes().length > NOTES_MAX) {
      tooLong.notes = NOTES_TOO_LONG;
    }
    if (close && this.nextNote().length > WEEK_NOTE_MAX) {
      tooLong.nextNote = NEXT_NOTE_TOO_LONG;
    }
    if (Object.keys(tooLong).length > 0) {
      this.errors.set(tooLong);
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
        verdict: asVerdict(this.verdict()),
        notes: this.notes().trim(),
      });
      switch (result.kind) {
        case 'ok':
          if (close) {
            this.closed.emit({ review: result.review, note: this.nextNote().trim() });
          } else {
            this.saved.emit(result.review);
          }
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

function asVerdict(value: string): WeekVerdict | null {
  return VERDICT_CHOICES.find((choice) => choice.value === value)?.value ?? null;
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
