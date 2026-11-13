export type Sport = 'running' | 'cycling' | 'swimming' | 'strength' | 'other';
export type ActivitySource = 'fit_file' | 'tcx_file';

/**
 * One lap of an activity. A value the file does not report is `null`; nothing is estimated.
 * `start_time` is an ISO 8601 timestamp in UTC.
 */
export interface Lap {
  start_time: string | null;
  elapsed_seconds: number | null;
  distance_m: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
}

/**
 * The summary of an imported activity, as the file reports it. A value the file does not report
 * is `null`. `start_time` and `created_at` are ISO 8601 timestamps in UTC; which local day an
 * activity belongs to is up to the caller.
 */
export interface Activity {
  id: string;
  source: ActivitySource;
  sport: Sport;
  /** The sport as the file calls it, kept when `sport` is `other`. */
  source_sport: string;
  start_time: string;
  elapsed_seconds: number | null;
  timer_seconds: number | null;
  distance_m: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  avg_power_w: number | null;
  total_ascent_m: number | null;
  calories: number | null;
  manufacturer: string;
  created_at: string;
}

export interface ActivityDetail extends Activity {
  laps: Lap[];
}

/** One page of the list, newest first. `count` is the number of all activities of the user. */
export interface ActivityPage {
  count: number;
  results: Activity[];
}

/** The session is gone or the request was refused (CSRF): the user has to sign in again. */
export interface Forbidden {
  kind: 'forbidden';
}

/** The activity does not exist (any more) or belongs to someone else. */
export interface NotFound {
  kind: 'not_found';
}

/** Too many imports in a minute; the server asks to wait. */
export interface RateLimited {
  kind: 'rate_limited';
}

export type ListActivitiesResult = { kind: 'ok'; page: ActivityPage } | Forbidden;

export type GetActivityResult = { kind: 'ok'; activity: ActivityDetail } | NotFound | Forbidden;

export type ImportActivityResult =
  | { kind: 'imported'; activity: Activity }
  /** The user has this activity already (the same file, or the same run in another format). */
  | { kind: 'duplicate'; existingId: string }
  /** The file cannot be imported; `message` is the server's text for users. */
  | { kind: 'rejected'; message: string }
  | { kind: 'too_large' }
  | RateLimited
  | Forbidden;

export type DeleteActivityResult = { kind: 'deleted' } | NotFound | Forbidden;
