import { DatePipe } from '@angular/common';
import { Component, inject, input, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { describeFailure } from '../../core/api/failures';
import { ReviewApi } from '../../core/review/review-api';
import {
  CoachComment as CoachCommentData,
  CommentProblem,
  WeekReview,
} from '../../core/review/review-models';
import { recommendationText } from './review-format';

const NOTHING_TO_REVIEW = 'There is nothing to look back on in this week yet.';
const NOT_CONFIGURED = 'No AI provider is set up.';
const NOT_USABLE = 'The coach did not give a comment that could be used. Please try again.';
const TOO_MANY = 'Too many requests. Please wait a minute and try again.';

/**
 * What the user's own coach says about a week: its comment and what it recommends for the next
 * week, and the button to ask for it. Asking takes a while (up to a minute or two) and costs the
 * user a request to their own AI provider, so it only ever happens when the button is pressed. The
 * comment is the coach's own text and is shown as text only. The component tells the page when it
 * starts and stops waiting (`busy`), so that nothing else is changed meanwhile.
 */
@Component({
  selector: 'app-coach-comment',
  imports: [DatePipe, RouterLink],
  templateUrl: './coach-comment.html',
  styleUrl: './coach-comment.css',
})
export class CoachComment {
  private readonly api = inject(ReviewApi);

  /** The Monday of the week, YYYY-MM-DD. */
  readonly week = input.required<string>();
  /** What the coach said when asked; `null`: it was not asked about this week. */
  readonly comment = input<CoachCommentData | null>(null);
  /** How many workouts of the week are still open: the week is not over. */
  readonly openWorkouts = input(0);
  /** Another action of the page is running: nothing may start. */
  readonly disabled = input(false);
  /** The coach commented; the whole week comes back with it. */
  readonly asked = output<WeekReview>();
  /** The week cannot be reviewed any more. */
  readonly notReviewable = output<void>();
  readonly signedOut = output<void>();
  /** The component waits for the coach (`true`) or has stopped waiting (`false`). */
  readonly busy = output<boolean>();

  protected readonly asking = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly problems = signal<CommentProblem[]>([]);
  /** The provider is not set up: the page says where to do it. */
  protected readonly needsProvider = signal(false);

  protected readonly recommendation = recommendationText;

  protected async ask(): Promise<void> {
    if (this.asking() || this.disabled()) {
      return;
    }
    this.message.set(null);
    this.problems.set([]);
    this.needsProvider.set(false);
    this.asking.set(true);
    this.busy.emit(true);
    try {
      const result = await this.api.askCoach(this.week());
      switch (result.kind) {
        case 'ok':
          this.asked.emit(result.review);
          break;
        case 'not_reviewable':
          this.notReviewable.emit();
          break;
        case 'nothing_to_review':
          this.message.set(NOTHING_TO_REVIEW);
          break;
        case 'not_configured':
          this.message.set(NOT_CONFIGURED);
          this.needsProvider.set(true);
          break;
        case 'not_usable':
          this.message.set(NOT_USABLE);
          this.problems.set(result.problems);
          break;
        case 'provider_problem':
          this.message.set(
            result.retry_after === null
              ? result.message
              : `${result.message} Try again in ${result.retry_after} seconds.`,
          );
          break;
        case 'rate_limited':
          this.message.set(TOO_MANY);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch (error) {
      this.message.set(describeFailure(error));
    } finally {
      this.asking.set(false);
      this.busy.emit(false);
    }
  }
}
