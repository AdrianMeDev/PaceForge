import { Activity } from '../../core/activities/activities-models';

/** Shown where the file does not report a value; nothing is estimated. */
export const MISSING = '–';

const SPORT_LABELS: Record<Activity['sport'], string> = {
  running: 'Running',
  cycling: 'Cycling',
  swimming: 'Swimming',
  strength: 'Strength',
  other: 'Other',
};

export function sportLabel(activity: Pick<Activity, 'sport' | 'source_sport'>): string {
  const label = SPORT_LABELS[activity.sport];
  return activity.sport === 'other' && activity.source_sport
    ? `${label} (${activity.source_sport})`
    : label;
}

export function sourceLabel(source: Activity['source']): string {
  return source === 'fit_file' ? 'FIT' : 'TCX';
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
