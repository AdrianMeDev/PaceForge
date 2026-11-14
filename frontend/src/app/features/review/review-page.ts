import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ReviewApi } from '../../core/review/review-api';
import {
  Comparison,
  CorrectResult,
  CorrectionField,
  ReviewActivity,
  ReviewWorkout,
  ReviewableWeek,
  WeekReview,
  WorkoutStatus,
} from '../../core/review/review-models';
import { dayLabel, minutesText, weekRange } from '../planning/plan-format';
import {
  NONE,
  AUTOMATIC,
  SPORT_LABELS,
  STATUS_CHOICES,
  STATUS_LABELS,
  activityChoiceText,
  activitySize,
  choiceOf,
  correctionOf,
  countAndMinutes,
  doneShareText,
  loadText,
  ratingText,
  statusChoiceOf,
  weekOptionText,
} from './review-format';
import { SessionRating } from './session-rating';
import { WeekFeedbackForm } from './week-feedback-form';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';
/** What the page is waiting for; one thing at a time. */
type Work = 'opening' | 'saving';

const FALLBACK = 'Something went wrong. Please try again.';
const REFRESH_FAILED = 'The list of weeks could not be refreshed. Please try again.';
const NOT_REVIEWABLE = 'This week cannot be reviewed.';
const NO_SUCH_WORKOUT = 'That workout is not in the plan of this week any more.';
const ACTIVITY_TAKEN = 'That activity is already assigned to another workout. Free it there first.';
const SAVED = 'Saved.';
const RATED = 'The rating was saved.';
const FEEDBACK_SAVED = 'Your feedback was saved.';
const NO_SUCH_ACTIVITY = 'That session does not exist any more.';
/** The fields of the correction, in the order a person reads them. */
const CORRECTION_FIELDS: readonly CorrectionField[] = ['activity', 'no_activity', 'status'];

/** One day of the plan with its workouts. */
interface ReviewDay {
  date: string;
  label: string;
  workouts: ReviewWorkout[];
}

/**
 * The week review: pick a week and see which activity belongs to which workout of the confirmed
 * plan, how each workout went, what was not planned and how planned and done compare. The server
 * works all of it out; the user can correct the match of a workout (an activity of their choice,
 * none, or a status), and the answer is always the whole week again. Titles and notes are the
 * user's own text and are shown as text only.
 */
@Component({
  selector: 'app-review-page',
  imports: [RouterLink, SessionRating, WeekFeedbackForm],
  templateUrl: './review-page.html',
  styleUrls: ['../auth/auth-form.css', './review-page.css'],
})
export class ReviewPage implements OnInit {
  private readonly api = inject(ReviewApi);

  protected readonly view = signal<View>('loading');
  protected readonly weeks = signal<ReviewableWeek[]>([]);
  protected readonly selected = signal('');
  protected readonly review = signal<WeekReview | null>(null);
  protected readonly work = signal<Work | null>(null);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);

  protected readonly days = computed<ReviewDay[]>(() => this.group(this.review()));
  protected readonly unplanned = computed(
    () => this.review()?.activities.filter((activity) => activity.workout_id === null) ?? [],
  );

  protected readonly sport = SPORT_LABELS;
  protected readonly status = STATUS_LABELS;
  protected readonly statusChoices = STATUS_CHOICES;
  protected readonly automatic = AUTOMATIC;
  protected readonly none = NONE;
  protected readonly range = weekRange;
  protected readonly weekOption = weekOptionText;
  protected readonly minutes = minutesText;
  protected readonly size = activitySize;
  protected readonly choice = activityChoiceText;
  protected readonly rating = ratingText;
  protected readonly loadOf = loadText;
  protected readonly counted = countAndMinutes;
  protected readonly share = doneShareText;
  protected readonly choiceOf = choiceOf;
  protected readonly statusChoiceOf = statusChoiceOf;
  protected readonly dayLabel = dayLabel;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const weeks = await this.api.weeks();
      if (weeks.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.weeks.set(weeks.weeks);
      // The latest week with a plan; the current week if none has one.
      const planned = [...weeks.weeks].reverse().find((week) => week.has_plan);
      this.selected.set((planned ?? weeks.weeks[weeks.weeks.length - 1])?.week_start ?? '');
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
      return;
    }
    if (this.selected() !== '') {
      await this.show();
    }
  }

  protected async selectWeek(value: string): Promise<void> {
    if (this.work() !== null || !this.weeks().some((week) => week.week_start === value)) {
      return;
    }
    this.clearMessages();
    this.review.set(null);
    this.selected.set(value);
    await this.show();
  }

  /** The choices of one workout as the server is to keep them; empty goes back to automatic. */
  protected async correct(workout: ReviewWorkout, choice: string, status: string): Promise<void> {
    if (this.work() !== null) {
      return;
    }
    this.clearMessages();
    this.work.set('saving');
    try {
      const result = await this.api.correct(
        this.selected(),
        workout.id,
        correctionOf(choice, status),
      );
      await this.afterCorrection(result);
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.work.set(null);
    }
  }

  /** A session was rated: the week is fetched again, as its load and totals follow the rating. */
  protected async rated(): Promise<void> {
    await this.reload([], RATED);
  }

  /** The session of a rating is gone (deleted elsewhere): the week shows what is left. */
  protected async gone(): Promise<void> {
    await this.reload([NO_SUCH_ACTIVITY], null);
  }

  protected feedbackSaved(review: WeekReview): void {
    this.errors.set([]);
    this.review.set(review);
    this.notice.set(FEEDBACK_SAVED);
  }

  protected async notReviewable(): Promise<void> {
    this.clearMessages();
    this.errors.set([NOT_REVIEWABLE]);
    await this.refresh();
  }

  protected signOut(): void {
    this.view.set('signed_out');
  }

  protected activityOf(workout: ReviewWorkout): ReviewActivity | null {
    return this.review()?.activities.find((item) => item.id === workout.activity_id) ?? null;
  }

  /** The statuses that occur, with how often, in the order of the workouts' life. */
  protected statusCounts(comparison: Comparison): { status: WorkoutStatus; count: number }[] {
    return (Object.keys(STATUS_LABELS) as WorkoutStatus[])
      .map((status) => ({ status, count: comparison.statuses[status] }))
      .filter((entry) => entry.count > 0);
  }

  private async afterCorrection(result: CorrectResult): Promise<void> {
    switch (result.kind) {
      case 'ok':
        this.review.set(result.review);
        this.notice.set(SAVED);
        break;
      case 'invalid':
        this.errors.set(
          result.message === null
            ? CORRECTION_FIELDS.flatMap((field) => result.errors[field] ?? [])
            : [result.message],
        );
        break;
      case 'activity_taken':
        this.errors.set([ACTIVITY_TAKEN]);
        break;
      case 'workout_not_found':
        this.errors.set([NO_SUCH_WORKOUT]);
        await this.fetch();
        break;
      case 'not_reviewable':
        this.errors.set([NOT_REVIEWABLE]);
        await this.refresh();
        break;
      case 'forbidden':
        this.view.set('signed_out');
        break;
    }
  }

  /** Fetches the selected week again; ``notice`` is shown if that worked. */
  private async reload(errors: string[], notice: string | null): Promise<void> {
    if (this.work() !== null) {
      return;
    }
    this.clearMessages();
    this.errors.set(errors);
    this.work.set('saving');
    try {
      await this.fetch();
      if (notice !== null && this.errors().length === 0) {
        this.notice.set(notice);
      }
    } finally {
      this.work.set(null);
    }
  }

  /** Opens the selected week and says what is wrong if that does not work. */
  private async show(): Promise<void> {
    this.work.set('opening');
    try {
      await this.fetch();
    } finally {
      this.work.set(null);
    }
  }

  private async fetch(): Promise<void> {
    try {
      const result = await this.api.week(this.selected());
      switch (result.kind) {
        case 'ok':
          this.review.set(result.review);
          break;
        case 'not_reviewable':
          this.review.set(null);
          this.errors.update((list) => [...list, NOT_REVIEWABLE]);
          await this.refresh();
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.update((list) => [...list, FALLBACK]);
    }
  }

  /** Fetches the weeks again without leaving the page; a failure is shown above the week. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.api.weeks();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.weeks.set(result.weeks);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private group(review: WeekReview | null): ReviewDay[] {
    const days: ReviewDay[] = [];
    for (const workout of review?.workouts ?? []) {
      let day = days.find((candidate) => candidate.date === workout.day);
      if (day === undefined) {
        day = { date: workout.day, label: dayLabel(workout.day), workouts: [] };
        days.push(day);
      }
      day.workouts.push(workout);
    }
    return days;
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
