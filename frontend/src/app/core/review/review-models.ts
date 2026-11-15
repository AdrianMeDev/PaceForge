import { ActivitySource, Sport as ActivitySport } from '../activities/activities-models';
import { Forbidden } from '../goals/goals-models';
import { RateLimited } from '../integrations/intervals-models';
import {
  ProviderProblem,
  Sport as PlannedSport,
  WorkoutGoal,
  WorkoutSlot,
} from '../planning/planning-models';

export type { Forbidden, RateLimited };

/**
 * How a workout went. `open` is only ever computed (its day has not passed and no activity
 * belongs to it yet): it cannot be chosen.
 */
export type WorkoutStatus = 'done' | 'partial' | 'missed' | 'replaced' | 'open';
/** What the user may set by hand. */
export type ChoosableStatus = 'done' | 'partial' | 'missed' | 'replaced';
/** Worked out by the server (`auto`) or decided by the user (`user`). */
export type Origin = 'auto' | 'user';

/** One week that can be reviewed (the current one and the four before it). */
export interface ReviewableWeek {
  /** The Monday, YYYY-MM-DD. */
  week_start: string;
  has_plan: boolean;
  workout_count: number;
  has_feedback: boolean;
}

/** The confirmed plan the review is about. */
export interface ReviewPlan {
  id: string;
  version: number;
  confirmed_at: string | null;
}

/**
 * A workout of the plan with how it went. `activity_origin` of `user` without an `activity_id`
 * means that the user said that no activity belongs to it. `title` and `notes` are free text:
 * show them as text only.
 */
export interface ReviewWorkout {
  id: string;
  day: string;
  position: number;
  sport: PlannedSport;
  title: string;
  goal: WorkoutGoal;
  duration_minutes: number;
  slot: WorkoutSlot | null;
  notes: string;
  status: WorkoutStatus;
  status_origin: Origin;
  activity_id: string | null;
  activity_origin: Origin | null;
}

/**
 * An activity of the week. `day` is its local day; `workout_id` is the workout it belongs to
 * (`null`: it was not planned). `notes` is free text: show it as text only. `load` is minutes
 * times RPE in arbitrary units (not TSS), `null` without a rating or a duration.
 */
export interface ReviewActivity {
  id: string;
  source: ActivitySource;
  sport: ActivitySport;
  start_time: string;
  day: string;
  elapsed_seconds: number | null;
  timer_seconds: number | null;
  distance_m: number | null;
  rpe: number | null;
  notes: string;
  load: number | null;
  workout_id: string | null;
}

/** Planned against actual. Actual minutes count every activity of the week, planned or not. */
export interface Figures {
  planned_count: number;
  planned_minutes: number;
  actual_count: number;
  actual_minutes: number;
  /** Sum of the loads of the rated sessions (AU, not TSS); `rated_count` says how many. */
  load: number;
  rated_count: number;
}

export interface SportFigures extends Figures {
  sport: ActivitySport;
}

export interface Comparison {
  sports: SportFigures[];
  total: Figures;
  statuses: Record<WorkoutStatus, number>;
  /** The share of workouts that are done among those that are not open; `null`: none judged. */
  done_percent: number | null;
}

/** How the user felt about the week: scales of 1 to 5, a note (free text). */
export interface WeekFeedback {
  fatigue: number | null;
  motivation: number | null;
  pain: number | null;
  notes: string;
  updated_at: string;
}

/** What the coach recommends for the volume of the next week. */
export type Recommendation = 'increase' | 'hold' | 'reduce';

/**
 * What the user's coach said about a week when asked. `comment` is the coach's own text, never
 * trusted: show it as text only. `created_at` is an ISO 8601 timestamp in UTC.
 */
export interface CoachComment {
  comment: string;
  next_week: Recommendation;
  created_at: string;
}

/** One week as the server worked it out; the workouts and activities are in order. */
export interface WeekReview {
  week_start: string;
  /** The day it is for the user now; days before it are over. */
  today: string;
  plan: ReviewPlan | null;
  workouts: ReviewWorkout[];
  activities: ReviewActivity[];
  comparison: Comparison;
  feedback: WeekFeedback | null;
  /** What the coach said when asked; `null`: it was not asked about this week. */
  comment: CoachComment | null;
}

/** What the user decides about one workout; everything empty goes back to the automatic match. */
export interface CorrectionInput {
  /** The activity that belongs to the workout, or `null`. */
  activity: string | null;
  /** Says that no activity belongs to it (not together with an `activity`). */
  no_activity: boolean;
  /** How it went; empty: worked out from the activity. */
  status: ChoosableStatus | '';
}

export interface FeedbackInput {
  fatigue: number | null;
  motivation: number | null;
  pain: number | null;
  notes: string;
}

/** The fields of the forms the server can name in a refusal. */
export type CorrectionField = 'activity' | 'no_activity' | 'status';
export type FeedbackField = 'fatigue' | 'motivation' | 'pain' | 'notes';

/** The week is not one that can be reviewed (not a Monday, too far back, or in the future). */
export interface NotReviewable {
  kind: 'not_reviewable';
}

export type ListReviewWeeksResult = { kind: 'ok'; weeks: ReviewableWeek[] } | Forbidden;

export type GetReviewResult = { kind: 'ok'; review: WeekReview } | NotReviewable | Forbidden;

export type CorrectResult =
  /** The whole week as it is now. */
  | { kind: 'ok'; review: WeekReview }
  | NotReviewable
  /** The workout is not in the confirmed plan of the week. */
  | { kind: 'workout_not_found' }
  /** The activity is already assigned by hand to another workout. */
  | { kind: 'activity_taken' }
  /** Refused: the messages by field, or `message` if none is for a field. */
  | {
      kind: 'invalid';
      errors: Partial<Record<CorrectionField, string[]>>;
      message: string | null;
    }
  | Forbidden;

export type SaveFeedbackResult =
  | { kind: 'ok'; review: WeekReview }
  | NotReviewable
  | {
      kind: 'invalid';
      errors: Partial<Record<FeedbackField, string[]>>;
      message: string | null;
    }
  | Forbidden;

/** What was wrong with an answer of the coach that could not be used (fixed texts only). */
export interface CommentProblem {
  path: string;
  message: string;
}

export type AskCoachResult =
  /** The whole week, with the comment of the coach in it. */
  | { kind: 'ok'; review: WeekReview }
  | NotReviewable
  /** The week has no confirmed plan, no activity and no feedback: there is nothing to ask about. */
  | { kind: 'nothing_to_review' }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** The coach gave no readable comment, even after being told what was wrong. */
  | { kind: 'not_usable'; problems: CommentProblem[] }
  /** The provider refused or could not be reached; `message` is the server's text for users. */
  | {
      kind: 'provider_problem';
      problem: ProviderProblem;
      message: string;
      retry_after: number | null;
    }
  /** Too many requests in a short time (this server's limit, not the provider's). */
  | RateLimited
  | Forbidden;
