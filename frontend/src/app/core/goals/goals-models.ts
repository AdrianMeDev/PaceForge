export type GoalKind = 'race' | 'threshold' | 'general';
export type GoalPriority = 'main' | 'secondary';
export type GoalStatus = 'active' | 'achieved' | 'dropped';
export type Discipline = 'running' | 'cycling' | 'swimming' | 'triathlon';
/** What a threshold goal raises: the FTP in watts or the running pace in seconds per kilometre. */
export type GoalMetric = 'ftp' | 'threshold_pace';

/**
 * A goal. Which fields apply depends on `kind`: a race has a date, a discipline and perhaps a
 * distance and a target time; a threshold goal has a metric and a target value; a general goal
 * has only a title and notes. What does not apply is `null`. Dates are calendar dates
 * (`2027-09-26`); `days_to_go` counts from today in the user's time zone and is negative after
 * the date.
 */
export interface Goal {
  id: string;
  kind: GoalKind;
  title: string;
  notes: string;
  priority: GoalPriority;
  status: GoalStatus;
  target_date: string | null;
  discipline: Discipline | null;
  /** Metres. */
  distance_m: number | null;
  /** Seconds. */
  target_time_seconds: number | null;
  metric: GoalMetric | null;
  target_value: number | null;
  days_to_go: number | null;
  /** ISO 8601 timestamps in UTC. */
  created_at: string;
  updated_at: string;
}

/** What is sent to create a goal. What is left out takes the server's default or stays empty. */
export interface GoalInput {
  kind: GoalKind;
  title: string;
  notes?: string;
  priority?: GoalPriority;
  status?: GoalStatus;
  target_date?: string | null;
  discipline?: Discipline | null;
  distance_m?: number | null;
  target_time_seconds?: number | null;
  metric?: GoalMetric | null;
  target_value?: number | null;
}

/** What is sent to change a goal: only the fields that change. The kind cannot be changed. */
export type GoalChanges = Partial<Omit<GoalInput, 'kind'>>;

/** The session is gone or the request was refused (CSRF): the user has to sign in again. */
export interface Forbidden {
  kind: 'forbidden';
}

/** The goal does not exist (any more) or belongs to someone else. */
export interface NotFound {
  kind: 'not_found';
}

/**
 * The input was refused. `fields` has the messages per field (`non_field_errors` for problems
 * of the whole goal, such as having too many); `errors` has all of them in one list.
 */
export interface Invalid {
  kind: 'invalid';
  errors: string[];
  fields: Record<string, string[]>;
}

export type ListGoalsResult = { kind: 'ok'; goals: Goal[] } | Forbidden;
export type CreateGoalResult = { kind: 'ok'; goal: Goal } | Invalid | Forbidden;
export type UpdateGoalResult = { kind: 'ok'; goal: Goal } | Invalid | NotFound | Forbidden;
export type DeleteGoalResult = { kind: 'deleted' } | NotFound | Forbidden;
