/** Which background jobs the signed-in user lets run for them. */
export interface JobSettings {
  sync: boolean;
  week_review: boolean;
  week_draft: boolean;
}

/** Which of the three jobs a run is about, in the order they run. */
export type JobName = 'sync' | 'week_review' | 'week_draft';

/** How an attempt ended. */
export type JobOutcome = 'done' | 'skipped' | 'failed';

/** The fixed words that say why a run was skipped or failed; empty when it simply succeeded. */
export type JobCode =
  | ''
  | 'not_connected'
  | 'invalid_key'
  | 'intervals_unavailable'
  | 'no_coach'
  | 'provider_error'
  | 'plan_not_usable'
  | 'comment_not_usable'
  | 'no_time'
  | 'nothing_to_review'
  | 'already_planned'
  | 'unexpected';

/** One logged job attempt, as the API lists it. */
export interface JobRun {
  id: string;
  job: JobName;
  /** The Monday of the week the job was about, or `null` for one about no week. YYYY-MM-DD. */
  week_start: string | null;
  /** ISO 8601 timestamps. */
  started_at: string;
  finished_at: string;
  outcome: JobOutcome;
  code: JobCode;
  /** Small numbers only, e.g. how many activities were new. */
  counts: Record<string, number>;
}

/** The session is gone or the request was refused (CSRF): the user has to sign in again. */
export interface Forbidden {
  kind: 'forbidden';
}

export type GetSettingsResult = { kind: 'ok'; settings: JobSettings } | Forbidden;

/** The API accepts any subset of the three flags. */
export type SettingsChanges = Partial<JobSettings>;

export type SaveSettingsResult = { kind: 'ok'; settings: JobSettings } | Forbidden;

export type ListRunsResult = { kind: 'ok'; runs: JobRun[] } | Forbidden;
