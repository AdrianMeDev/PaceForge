import { Activity, LoadSource } from '../../core/activities/activities-models';

/** Shown where the file does not report a value; nothing is estimated. */
export const MISSING = '–';

const SPORT_LABELS: Record<Activity['sport'], string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength',
  other: 'Other',
};

/** The choices of the filter of the list: every sport the server knows. */
export const SPORT_CHOICES = (Object.keys(SPORT_LABELS) as Activity['sport'][]).map((value) => ({
  value,
  label: SPORT_LABELS[value],
}));

export function sportLabel(activity: Pick<Activity, 'sport' | 'source_sport'>): string {
  const label = SPORT_LABELS[activity.sport];
  return activity.sport === 'other' && activity.source_sport
    ? `${label} (${activity.source_sport})`
    : label;
}

const SOURCE_LABELS: Record<Activity['source'], string> = {
  fit_file: 'FIT',
  tcx_file: 'TCX',
  gpx_file: 'GPX',
  manual: 'Entered by hand',
  intervals_icu: 'Intervals.icu',
};

export function sourceLabel(source: Activity['source']): string {
  return SOURCE_LABELS[source];
}

/** `7` for the rating of the user, `–` where they gave none. */
export function formatRpe(rpe: number | null): string {
  return rpe === null ? MISSING : String(rpe);
}

/** Unified load points with the source used by the server; a dash when unknown. */
export function formatLoad(load: number | null, source: LoadSource | null): string {
  if (load === null) {
    return MISSING;
  }
  const context = source === 'intervals' ? 'Intervals.icu' : source === 'rpe' ? 'RPE estimate' : '';
  return `${load} pts${context ? ` (${context})` : ''}`;
}

/** `55:29` below an hour, `1:05:05` from an hour on. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return MISSING;
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, '0');
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`;
}

export function formatDistance(meters: number | null): string {
  return meters === null ? MISSING : `${(meters / 1000).toFixed(2)} km`;
}

export function formatHeartRate(bpm: number | null): string {
  return bpm === null ? MISSING : `${bpm} bpm`;
}
