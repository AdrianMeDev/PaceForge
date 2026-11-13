import { Metric, ThresholdSource, Zone } from '../../core/athlete/athlete-models';

/**
 * What a person can plausibly enter. The server checks again with the same ranges; checking here
 * only saves a round trip and gives the message next to the field.
 */
const RANGES: Record<Metric, { min: number; max: number; unit: string }> = {
  ftp: { min: 30, max: 2000, unit: 'W' },
  lthr: { min: 30, max: 250, unit: 'bpm' },
  max_hr: { min: 30, max: 250, unit: 'bpm' },
  threshold_pace: { min: 120, max: 1200, unit: 's/km' },
};

export const METRIC_LABELS: Record<Metric, string> = {
  ftp: 'FTP',
  lthr: 'Lactate threshold heart rate',
  max_hr: 'Maximum heart rate',
  threshold_pace: 'Threshold pace',
};

export const SOURCE_LABELS: Record<ThresholdSource, string> = {
  manual: 'You',
  intervals: 'Intervals.icu',
  estimated: 'Estimated',
};

export type ParsedInput = { ok: true; value: number } | { ok: false; error: string };

const PACE_HELP = 'Enter the pace as minutes and seconds per kilometre, for example 5:00.';

/**
 * Turns what the user typed into the number the server expects: watts or beats as a number (a
 * comma works as the decimal separator), the pace as `m:ss` (sent as seconds per kilometre).
 */
export function parseThreshold(metric: Metric, text: string): ParsedInput {
  const input = text.trim();
  if (!input) {
    return fail('Enter a value.');
  }
  if (metric === 'threshold_pace') {
    return parsePace(input);
  }
  const normalised = input.replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(normalised)) {
    return fail('Enter a number, for example 250.');
  }
  const value = Number(normalised);
  const { min, max, unit } = RANGES[metric];
  return value >= min && value <= max
    ? { ok: true, value }
    : fail(`Enter a value between ${min} and ${max} ${unit}.`);
}

function parsePace(input: string): ParsedInput {
  const match = /^(\d{1,2}):([0-5]\d)$/.exec(input);
  if (!match) {
    return fail(PACE_HELP);
  }
  const seconds = Number(match[1]) * 60 + Number(match[2]);
  const { min, max } = RANGES.threshold_pace;
  return seconds >= min && seconds <= max
    ? { ok: true, value: seconds }
    : fail(`Enter a pace between ${formatPace(min)} and ${formatPace(max)} per km.`);
}

function fail(error: string): ParsedInput {
  return { ok: false, error };
}

/** `m:ss`, from seconds per kilometre rounded half up. */
export function formatPace(seconds: number): string {
  const total = Math.floor(seconds + 0.5);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export function formatValue(metric: Metric, value: number): string {
  switch (metric) {
    case 'ftp':
      return `${Math.floor(value + 0.5)} W`;
    case 'threshold_pace':
      return `${formatPace(value)} /km`;
    default:
      return `${Math.floor(value + 0.5)} bpm`;
  }
}

/** The value as it is typed into the field: the pace as `m:ss`, everything else as a number. */
export function inputText(metric: Metric, value: number): string {
  return metric === 'threshold_pace' ? formatPace(value) : String(Math.floor(value + 0.5));
}

/**
 * A zone as a range for people. Zones are half open (the upper bound belongs to the next zone),
 * so the last value of a zone is one below its upper bound. Pace zones run from slow to fast.
 */
export function describeZone(zone: Zone): string {
  const { lower, upper, unit } = zone;
  if (unit === 's/km') {
    if (lower !== null && upper === null) {
      return `${formatPace(lower)} /km or slower`;
    }
    if (lower === null && upper !== null) {
      return `faster than ${formatPace(upper)} /km`;
    }
    return `${formatPace(lower ?? 0)}–${formatPace((upper ?? 0) - 1)} /km`;
  }
  if (lower === null && upper !== null) {
    return `below ${upper} ${unit}`;
  }
  if (lower !== null && upper === null) {
    return `${lower} ${unit} and above`;
  }
  return `${lower}–${(upper ?? 0) - 1} ${unit}`;
}
