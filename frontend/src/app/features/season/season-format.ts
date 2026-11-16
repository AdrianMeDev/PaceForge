import {
  Focus,
  KeySession,
  RacePriority,
  SeasonPhase,
  SeasonRace,
  SessionKind,
  Sport,
} from '../../core/season/season-models';
import { formatGoalDistance } from '../goals/goal-format';
import { SPORT_LABELS, minutesText, weekRange } from '../planning/plan-format';

export const PHASE_LABELS: Record<SeasonPhase, string> = {
  base: 'Base',
  build: 'Build',
  specific: 'Specific',
  taper: 'Taper',
  transition: 'Transition',
};

/** What each phase is for, in a few words (shown as a hint under the table). */
export const PHASE_HINTS: Record<SeasonPhase, string> = {
  base: 'Build the volume at an easy effort.',
  build: 'Keep adding volume and start to add quality.',
  specific: 'Train for the demands of the race; the volume stays where it is.',
  taper: 'Less volume, the intensity stays, so you arrive fresh.',
  transition: 'Rest after the main race before building up again.',
};

/** The letter of a priority: A is the main goal, B a secondary goal, C a preparation race. */
export const PRIORITY_LETTERS: Record<RacePriority, string> = {
  main: 'A',
  secondary: 'B',
  preparation: 'C',
};

/** "A · Berlin Marathon · 42.2 km": a race in a line; the distance only if there is one. */
export function raceText(race: SeasonRace): string {
  const parts = [PRIORITY_LETTERS[race.priority], race.title];
  if (race.distance_m !== null) {
    parts.push(formatGoalDistance(race.distance_m));
  }
  return parts.join(' · ');
}

/** The calendar day of `now` on this device, `YYYY-MM-DD` (the week that is marked as this one). */
export function localToday(now: Date = new Date()): string {
  const pad = (value: number): string => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** "70 %": the share of what the week offers that the skeleton plans; empty if it offers nothing. */
export function usedShare(target: number, capacity: number): string {
  return capacity > 0 ? `${Math.round((target / capacity) * 100)} %` : '';
}

export const FOCUS_LABELS: Record<Focus, string> = {
  recovery: 'Recovery',
  endurance: 'Endurance',
  tempo: 'Tempo',
  threshold: 'Threshold',
  vo2max: 'VO2max',
  race_specific: 'Race specific',
};

export const KIND_LABELS: Record<SessionKind, string> = {
  long: 'Long',
  tempo: 'Tempo',
  threshold: 'Threshold',
  vo2max: 'VO2max',
  race_pace: 'Race pace',
  strength: 'Strength',
  race: 'Race',
};

const SPORT_ORDER: Sport[] = ['running', 'cycling', 'swimming', 'strength'];

/** "Running 3 h · Cycling 1 h 30 min": what a week plans of each sport, empty if nothing. */
export function minutesBySport(minutes: Partial<Record<Sport, number>>): string {
  return SPORT_ORDER.filter((sport) => (minutes[sport] ?? 0) > 0)
    .map((sport) => `${SPORT_LABELS[sport]} ${minutesText(minutes[sport] as number)}`)
    .join(' · ');
}

/** "Running · Long · 1 h 30 min · 3 x 10 min": a key session in a line; the detail only if given. */
export function keySessionText(session: KeySession): string {
  const parts = [
    SPORT_LABELS[session.sport],
    KIND_LABELS[session.kind],
    minutesText(session.minutes),
  ];
  if (session.detail !== '') {
    parts.push(session.detail);
  }
  return parts.join(' · ');
}

/**
 * Where a finding of the checks points: "16 Nov – 22 Nov" for a path into a week (`weeks[3]…`, the
 * weeks as they are shown) and "Season" for anything else.
 */
export function seasonFindingPlace(path: string, weekStarts: string[]): string {
  const match = /^weeks\[(\d+)\]/.exec(path);
  const start = match === null ? undefined : weekStarts[Number(match[1])];
  return start === undefined ? 'Season' : weekRange(start);
}
