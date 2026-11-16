import { Forbidden } from '../goals/goals-models';

export type { Forbidden };

/** What a week of the season is for. `transition` is the rest after the main race. */
export type SeasonPhase = 'base' | 'build' | 'specific' | 'taper' | 'transition';

/** A, B or C: the main goal, a secondary goal or a preparation race. */
export type RacePriority = 'main' | 'secondary' | 'preparation';

/** A race in a week of the season. The title is the athlete's own text. */
export interface SeasonRace {
  /** The day of the race, `YYYY-MM-DD`. */
  date: string;
  priority: RacePriority;
  discipline: 'running' | 'cycling' | 'swimming' | 'triathlon' | null;
  /** In metres; `null`: not said. */
  distance_m: number | null;
  title: string;
}

/** One week of the skeleton. `week_start` is a Monday, `YYYY-MM-DD`. */
export interface SeasonWeek {
  week_start: string;
  phase: SeasonPhase;
  /** A recovery week of the building weeks. */
  recovery: boolean;
  /** The minutes the skeleton plans for the week, never above `capacity_minutes`. */
  target_minutes: number;
  /** The minutes the week offers (absences taken out, the weekly budget applied). */
  capacity_minutes: number;
  races: SeasonRace[];
}

/**
 * The skeleton of the season: the weeks up to the last A or B race, worked out by the server on
 * every request. `rolling`: there is no race to work towards (twelve weeks of base and build);
 * `truncated`: the last race lies beyond a year and the skeleton stops before it.
 */
export interface Season {
  rolling: boolean;
  truncated: boolean;
  /** The race the phases are counted back from; `null` for a rolling skeleton. */
  main_race: SeasonRace | null;
  peak_minutes: number;
  weeks: SeasonWeek[];
}

export type GetSeasonResult = { kind: 'ok'; season: Season } | Forbidden;
