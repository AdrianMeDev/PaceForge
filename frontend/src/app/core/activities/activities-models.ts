export type Sport = 'running' | 'cycling' | 'swimming' | 'strength' | 'other';
export type ActivitySource = 'fit_file' | 'tcx_file' | 'gpx_file' | 'manual' | 'intervals_icu';
export type LoadSource = 'intervals' | 'rpe';

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
  avg_pace_s_per_km: number | null;
  avg_power_w: number | null;
  total_ascent_m: number | null;
  calories: number | null;
  /** Raw training load reported by the source (e.g. Intervals.icu). */
  training_load: number | null;
  manufacturer: string;
  /** How hard the user felt the session was, 1 to 10 (their own rating); `null`: not said. */
  rpe: number | null;
  /** The user's own note (free text: show it as text only). */
  notes: string;
  /** Unified load points: Intervals load, otherwise hours × RPE × 10; `null` if unknown. */
  load: number | null;
  load_source: LoadSource | null;
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

/** Intervals.icu cannot be reached or answered oddly. `message` is the server's text for users. */
export interface Unavailable {
  kind: 'unavailable';
  message: string;
}

export type SyncActivitiesResult =
  | {
      kind: 'ok';
      imported: number;
      skipped_duplicates: number;
      skipped_strava: number;
      skipped_invalid: number;
      wellness_synced: number;
      last_sync_at: string | null;
    }
  | { kind: 'not_connected' }
  | { kind: 'invalid_key' }
  | RateLimited
  | Unavailable
  | Forbidden;

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

/** What the form sends. `date` is YYYY-MM-DD and `time` HH:MM on the wall clock of the user. */
export interface ManualActivityInput {
  sport: Sport;
  date: string;
  time: string;
  duration_minutes: number;
  distance_km: number | null;
  rpe: number | null;
  notes: string;
}

/** The fields of the form the server can name in a refusal. */
export type ManualField =
  'sport' | 'date' | 'time' | 'duration_minutes' | 'distance_km' | 'rpe' | 'notes';

export type EnterActivityResult =
  | { kind: 'entered'; activity: Activity }
  /** The user has this session already (as a file, a sync or an earlier entry). */
  | { kind: 'duplicate'; existingId: string }
  /** The server refused the input: the messages by field, or `message` if none is for a field. */
  | { kind: 'invalid'; errors: Partial<Record<ManualField, string[]>>; message: string | null }
  | RateLimited
  | Forbidden;

export type DeleteActivityResult = { kind: 'deleted' } | NotFound | Forbidden;

/** What the user may change about an activity afterwards: how hard it felt, and a note. */
export interface RatingInput {
  /** 1 to 10, or `null` to clear it. */
  rpe: number | null;
  /** Up to 500 characters; empty clears it. */
  notes: string;
}

export type RatingField = 'rpe' | 'notes';

export type RateActivityResult =
  /** The activity as it is now, with its load following the rating. */
  | { kind: 'ok'; activity: ActivityDetail }
  | NotFound
  /** The server refused the input: the messages by field, or `message` if none is for a field. */
  | { kind: 'invalid'; errors: Partial<Record<RatingField, string[]>>; message: string | null }
  | Forbidden;
