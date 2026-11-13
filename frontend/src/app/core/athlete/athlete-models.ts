export type SportGroup = 'ride' | 'run';
export type Metric = 'ftp' | 'lthr' | 'max_hr' | 'threshold_pace';

/** Cycling has power, running has pace; both have the heart rates. */
export type MetricOf<S extends SportGroup> = S extends 'ride'
  ? 'ftp' | 'lthr' | 'max_hr'
  : 'threshold_pace' | 'lthr' | 'max_hr';

/** Where a value comes from. When several exist, `manual` counts first, then `intervals`. */
export type ThresholdSource = 'manual' | 'intervals' | 'estimated';

/**
 * One value of a threshold. Units: watts for `ftp`, beats per minute for `lthr` and `max_hr`,
 * seconds per kilometre for `threshold_pace`. `basis` is a short fixed text on how it came about
 * (empty for a value the user typed in); `updated_at` is an ISO 8601 timestamp in UTC.
 */
export interface ThresholdValue {
  value: number;
  source: ThresholdSource;
  basis: string;
  updated_at: string;
}

/** `effective` is the value that counts, and always the first of `candidates`. */
export interface Threshold {
  effective: ThresholdValue | null;
  candidates: ThresholdValue[];
}

export type ZoneUnit = 'W' | 'bpm' | 's/km';

/**
 * A training zone, half open: `lower` is included, `upper` is not, `null` means no limit on that
 * side. Pace is time per distance, so pace zones run from slow to fast and their bounds fall.
 */
export interface Zone {
  number: number;
  name: string;
  lower: number | null;
  upper: number | null;
  unit: ZoneUnit;
}

/** The zones together with the threshold they are based on. */
export interface ZoneSet {
  basis: Metric;
  zones: Zone[];
}

export interface RideProfile {
  thresholds: { ftp: Threshold; lthr: Threshold; max_hr: Threshold };
  zones: { power: ZoneSet | null; heart_rate: ZoneSet | null };
}

export interface RunProfile {
  thresholds: { threshold_pace: Threshold; lthr: Threshold; max_hr: Threshold };
  zones: { pace: ZoneSet | null; heart_rate: ZoneSet | null };
}

export interface AthleteProfile {
  /** An IANA name such as `Europe/Berlin`; empty if the user has not set one. */
  timezone: string;
  intervals: {
    /** A working Intervals.icu connection exists (a refused key does not count). */
    connected: boolean;
    /** When the thresholds were last read from Intervals.icu (ISO 8601, UTC), or never. */
    synced_at: string | null;
  };
  sports: { ride: RideProfile; run: RunProfile };
}

/** The session is gone or the request was refused (CSRF): the user has to sign in again. */
export interface Forbidden {
  kind: 'forbidden';
}

/** That threshold does not exist (cycling has no pace, running has no power). */
export interface NotFound {
  kind: 'not_found';
}

/** The input was refused; `errors` are messages for the user. */
export interface Invalid {
  kind: 'invalid';
  errors: string[];
}

/** Too many calls to Intervals.icu; the server asks to wait. */
export interface RateLimited {
  kind: 'rate_limited';
}

/** Every successful change answers with the whole profile. */
export type GetAthleteResult = { kind: 'ok'; profile: AthleteProfile } | Forbidden;
export type SetTimezoneResult = { kind: 'ok'; profile: AthleteProfile } | Invalid | Forbidden;
export type SetThresholdResult =
  { kind: 'ok'; profile: AthleteProfile } | Invalid | NotFound | Forbidden;
export type ClearThresholdResult = { kind: 'ok'; profile: AthleteProfile } | NotFound | Forbidden;

export type SyncResult =
  | { kind: 'ok'; profile: AthleteProfile }
  | { kind: 'not_connected' }
  /** Intervals.icu did not accept the stored key; the connection needs attention. */
  | { kind: 'key_refused'; message: string }
  | RateLimited
  /** Intervals.icu cannot be reached or answered oddly; `message` is the server's text. */
  | { kind: 'unavailable'; message: string }
  | Forbidden;
