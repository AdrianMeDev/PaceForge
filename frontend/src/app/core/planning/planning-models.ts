import { Forbidden } from '../goals/goals-models';
import { RateLimited } from '../integrations/intervals-models';

export type { Forbidden, RateLimited };

export type Sport = 'running' | 'cycling' | 'swimming' | 'strength';
export type WorkoutGoal =
  'recovery' | 'endurance' | 'tempo' | 'threshold' | 'vo2max' | 'strength' | 'other';
export type ZoneSystem = 'power' | 'heart_rate' | 'pace';
export type SegmentKind = 'warmup' | 'steady' | 'work' | 'recovery' | 'cooldown';
/** A plan is a `draft` until it is decided on; only a draft can be confirmed or discarded. */
export type PlanStatus = 'draft' | 'confirmed' | 'superseded' | 'discarded';
/** An `error` keeps a plan from being confirmed, a `warning` is for the user to weigh. */
export type Severity = 'error' | 'warning';
/** What went wrong at the provider when a plan was drafted (the server's fixed texts come along). */
export type ProviderProblem =
  'invalid_key' | 'rate_limited' | 'unavailable' | 'unexpected' | 'not_allowed';

/** One part of a workout, done `repeat` times in a row; zone system and zone come together. */
export interface Segment {
  kind: SegmentKind;
  seconds: number;
  repeat: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
}

/** A planned session. `day` is a calendar date (YYYY-MM-DD); the text is the coach's. */
export interface Workout {
  day: string;
  sport: Sport;
  title: string;
  goal: WorkoutGoal;
  duration_minutes: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
  notes: string;
  segments: Segment[];
}

/** What a check says about a plan. `path` points into the plan (`workouts[2].segments`). */
export interface Finding {
  severity: Severity;
  code: string;
  message: string;
  path: string;
}

/** The checks of a draft. `valid` means there is no error; warnings may remain. */
export interface Report {
  valid: boolean;
  findings: Finding[];
}

/** One version of a week in the list. Timestamps are ISO 8601. */
export interface PlanVersion {
  id: string;
  version: number;
  status: PlanStatus;
  reason: string;
  workout_count: number;
  created_at: string;
  confirmed_at: string | null;
}

/** A week that can be planned (`week_start` is its Monday), newest version first. */
export interface PlannableWeek {
  week_start: string;
  plans: PlanVersion[];
}

/**
 * A plan with its workouts, by day. Only a draft has a `report`; `confirmed_at` is set for a
 * confirmed plan and for one that has been replaced since. `parent` is the version it replaces.
 */
export interface WeekPlan {
  id: string;
  week_start: string;
  version: number;
  status: PlanStatus;
  reason: string;
  rationale: string;
  parent: string | null;
  created_at: string;
  confirmed_at: string | null;
  workouts: Workout[];
  report: Report | null;
}

/** What was wrong with an answer of the coach that could not be used (fixed texts only). */
export interface PlanProblem {
  path: string;
  message: string;
}

/** The plan does not exist (any more) or belongs to someone else. */
export interface PlanNotFound {
  kind: 'not_found';
}

/** Only a draft can be confirmed or discarded. */
export interface NotADraft {
  kind: 'not_a_draft';
}

export type ListWeeksResult = { kind: 'ok'; weeks: PlannableWeek[] } | Forbidden;

export type GenerateResult =
  /** A draft was stored (version 1 or newer); its checks may still have errors. */
  | { kind: 'ok'; plan: WeekPlan }
  /** The week is not one that can be planned. */
  | { kind: 'not_plannable' }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** The coach gave no readable plan, even after being told what was wrong. */
  | { kind: 'not_usable'; problems: PlanProblem[] }
  /** The provider refused or could not be reached; `message` is the server's text for users. */
  | {
      kind: 'provider_problem';
      problem: ProviderProblem;
      message: string;
      retry_after: number | null;
    }
  /** Too many plans requested in a short time (this server's limit, not the provider's). */
  | RateLimited
  | Forbidden;

export type GetPlanResult = { kind: 'ok'; plan: WeekPlan } | PlanNotFound | Forbidden;

export type ConfirmPlanResult =
  | { kind: 'ok'; plan: WeekPlan }
  | PlanNotFound
  | NotADraft
  /** The plan has errors; `findings` has all checks, the errors among them. */
  | { kind: 'not_confirmable'; findings: Finding[] }
  | Forbidden;

export type DiscardPlanResult =
  { kind: 'ok'; plan: WeekPlan } | PlanNotFound | NotADraft | Forbidden;
