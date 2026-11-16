import { RacePriority, SeasonPhase, SeasonRace } from '../../core/season/season-models';
import { formatGoalDistance } from '../goals/goal-format';

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

/** "70 %": the share of what the week offers that the skeleton plans; empty if it offers nothing. */
export function usedShare(target: number, capacity: number): string {
  return capacity > 0 ? `${Math.round((target / capacity) * 100)} %` : '';
}
