import { Forbidden } from '../goals/goals-models';
import type { SeasonWeekFacts } from '../season/season-models';
import { RateLimited } from '../integrations/intervals-models';

export type { Forbidden, RateLimited };

export type Sport = 'running' | 'cycling' | 'swimming' | 'strength';
export type WorkoutGoal =
  'recovery' | 'endurance' | 'tempo' | 'threshold' | 'vo2max' | 'strength' | 'other';
export type ZoneSystem = 'power' | 'heart_rate' | 'pace';
/** When on the day a workout is done; only the order is meant, there is no clock time. */
export type WorkoutSlot = 'morning' | 'afternoon' | 'evening';
export type SegmentKind = 'warmup' | 'steady' | 'work' | 'recovery' | 'cooldown';
/** A plan is a `draft` until it is decided on; only a draft can be confirmed or discarded. */
export type PlanStatus = 'draft' | 'confirmed' | 'superseded' | 'discarded';
/** An `error` keeps a plan from being confirmed, a `warning` is for the user to weigh. */
export type Severity = 'error' | 'warning';
/** What went wrong at the provider when a plan was drafted (the server's fixed texts come along). */
export type ProviderProblem =
  'invalid_key' | 'rate_limited' | 'unavailable' | 'unexpected' | 'not_allowed';

/** What a zone means in numbers: a closed range in watts, beats per minute or seconds per km. */
export type TargetUnit = 'W' | 'bpm' | 's/km';

/** For pace `low` is the faster end (fewer seconds). `null` where no threshold is known. */
export interface ZoneTarget {
  low: number;
  high: number;
  unit: TargetUnit;
}

/** Whether the event of a workout is in the Intervals.icu calendar. */
export type ExportStatus = 'not_sent' | 'synced' | 'failed';
/** Why sending a workout failed; the server's fixed codes. Empty when it did not. */
export type ExportError = '' | 'rejected' | 'unavailable' | 'unexpected';
/** Why a week could not be sent at all. */
export type PushProblem = 'not_confirmed' | 'not_connected' | 'invalid_key' | 'unexpected';

/** Where one workout stands with Intervals.icu; `pushed_at` is the last attempt (ISO 8601). */
export interface WorkoutExport {
  status: ExportStatus;
  error_code: ExportError;
  pushed_at: string | null;
}

/** The workouts of a confirmed plan by state; `older` events of an earlier version remain. */
export interface ExportSummary {
  synced: number;
  failed: number;
  not_sent: number;
  older: number;
}

/** What a push did, or why it could not be made (the server's text for users). */
export type PushOutcome =
  | { ok: true; synced: number; failed: number; removed: number; left_behind: number }
  | { ok: false; problem: PushProblem; message: string };

/** What an exercise trains. */
export type ExerciseRegion = 'legs' | 'core' | 'upper_body' | 'full_body';
/** What an exercise needs. */
export type ExerciseEquipment = 'gym' | 'dumbbells' | 'bodyweight';

/**
 * One exercise of a strength workout: `sets` of `reps` repetitions, or of a hold of `seconds`
 * (exactly one of the two is set). The name is the coach's text.
 */
export interface Exercise {
  name: string;
  region: ExerciseRegion;
  equipment: ExerciseEquipment;
  sets: number;
  reps: number | null;
  seconds: number | null;
  /** How hard it is, 1 to 10; `null`: not said. */
  rpe: number | null;
  /** The rest between sets in seconds; `null`: not said. */
  rest_seconds: number | null;
}

/** One part of a workout, done `repeat` times in a row; zone system and zone come together. */
export interface Segment {
  kind: SegmentKind;
  seconds: number;
  repeat: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
  target: ZoneTarget | null;
}

/**
 * A planned session. `day` is a calendar date (YYYY-MM-DD); the text is the coach's. `lineage` says
 * which training this is across the versions of a week: a version made from another keeps it.
 */
export interface Workout {
  lineage: string;
  day: string;
  sport: Sport;
  title: string;
  goal: WorkoutGoal;
  duration_minutes: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
  /** The zone as numbers, as it is now (the thresholds may change); `null` without one. */
  target: ZoneTarget | null;
  /** Only a confirmed plan is sent: `null` for any other. */
  export: WorkoutExport | null;
  notes: string;
  /** When on the day; `null`: not said. */
  slot: WorkoutSlot | null;
  /** Stretching added to this workout in minutes (0: none): never a workout of its own. */
  stretching_minutes: number;
  segments: Segment[];
  /** The exercises of a strength workout, in the order they are done; empty for any other. */
  exercises: Exercise[];
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
  /** What the confirmed season plan says about the week; `null`: nothing (no plan, or not in it). */
  season: SeasonWeekFacts | null;
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
  /** What the user wrote about the week when asking for this draft; empty if nothing. Free text. */
  note: string;
  rationale: string;
  parent: string | null;
  created_at: string;
  confirmed_at: string | null;
  workouts: Workout[];
  report: Report | null;
  /** Only for a confirmed plan. */
  export: ExportSummary | null;
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
  /** The note was refused (too long, not plain text); `message` is the server's text for users. */
  | { kind: 'invalid'; message: string }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** The week offers no training time at all; nothing was asked of the coach. */
  | { kind: 'no_time' }
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
  /** `push` is what sending the week did, if that was asked for. */
  | { kind: 'ok'; plan: WeekPlan; push: PushOutcome | null }
  | PlanNotFound
  | NotADraft
  /** The plan has errors; `findings` has all checks, the errors among them. */
  | { kind: 'not_confirmable'; findings: Finding[] }
  | Forbidden;

export type PushPlanResult =
  /** The week was sent; single workouts may still have failed (see their `export`). */
  | { kind: 'ok'; plan: WeekPlan; push: PushOutcome }
  /** Nothing was sent: `problem` says why and `message` is the server's text for users. */
  | { kind: 'problem'; problem: PushProblem; message: string }
  | PlanNotFound
  /** Too many pushes in a short time (this server's limit). */
  | RateLimited
  | Forbidden;

export type DiscardPlanResult =
  { kind: 'ok'; plan: WeekPlan } | PlanNotFound | NotADraft | Forbidden;

/** A part of a workout as it is sent: no `target`, which the server works out. */
export interface EditedSegment {
  kind: SegmentKind;
  seconds: number;
  repeat: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
}

/**
 * A workout as it is sent when a plan is changed by hand. `lineage` is the lineage of the workout
 * of the plan that is changed this one is made from, `null` for a new one.
 */
export interface EditedWorkout {
  lineage: string | null;
  day: string;
  sport: Sport;
  title: string;
  goal: WorkoutGoal;
  duration_minutes: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
  notes: string;
  slot: WorkoutSlot | null;
  stretching_minutes: number;
  segments: EditedSegment[];
  exercises: Exercise[];
}

/** A plan as it is sent to be checked or stored: the plan format, with the workouts by lineage. */
export interface EditedPlan {
  week_start: string;
  rationale: string;
  workouts: EditedWorkout[];
}

/** The week cannot be planned (any more), so it cannot be changed either. */
export interface NotPlannable {
  kind: 'not_plannable';
}

/** What was wrong with the plan that was sent (fixed texts, by path). */
export interface InvalidPlan {
  kind: 'invalid';
  problems: PlanProblem[];
}

export type CheckPlanResult =
  /** `order[i]` is the place in what was sent of the workout that the findings call `i`. */
  { kind: 'ok'; report: Report; order: number[] } | NotPlannable | InvalidPlan | Forbidden;

export type RevisePlanResult =
  /** The new draft, with its checks (it may have errors). */
  | { kind: 'ok'; plan: WeekPlan }
  | PlanNotFound
  | NotPlannable
  /** Only a draft or a confirmed plan can be changed. */
  | { kind: 'not_revisable' }
  | InvalidPlan
  | Forbidden;

export type RestorePlanResult =
  /** The new draft, checked with today's data. */
  | { kind: 'ok'; plan: WeekPlan }
  | PlanNotFound
  | NotPlannable
  /** Only a version that was replaced or discarded can be restored. */
  | { kind: 'not_restorable' }
  | Forbidden;
