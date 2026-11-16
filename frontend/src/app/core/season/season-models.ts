import { Forbidden } from '../goals/goals-models';
import { PlanStatus, Report, Sport } from '../planning/planning-models';

export type { Forbidden, PlanStatus, Report, Sport };

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

/** What a week of a filled season is about. */
export type Focus = 'recovery' | 'endurance' | 'tempo' | 'threshold' | 'vo2max' | 'race_specific';

/** What a key session is. */
export type SessionKind =
  'long' | 'tempo' | 'threshold' | 'vo2max' | 'race_pace' | 'strength' | 'race';

/** A session a week stands on. `detail` is the coach's own text ("3 x 10 min"), maybe empty. */
export interface KeySession {
  sport: Sport;
  kind: SessionKind;
  minutes: number;
  detail: string;
}

/**
 * One week as the coach filled it: the minutes of each sport it plans (a sport left out has
 * none), the focus, up to three key sessions and the reason, which is the coach's own text.
 * `total_minutes` is the sum of `minutes`.
 */
export interface PlanWeek {
  week_start: string;
  minutes: Partial<Record<Sport, number>>;
  total_minutes: number;
  focus: Focus;
  key_sessions: KeySession[];
  reason: string;
}

/** One version of the season plan in the list. Timestamps are ISO 8601. */
export interface SeasonPlanVersion {
  id: string;
  version: number;
  status: PlanStatus;
  reason: string;
  week_count: number;
  created_at: string;
  confirmed_at: string | null;
}

/**
 * A version of the season plan with its weeks and the skeleton it was made for (which may differ
 * from today's). Only a draft has a `report`; `confirmed_at` is set for a confirmed version and
 * for one that has been replaced since. `parent` is the version it replaces.
 */
export interface SeasonPlan {
  id: string;
  version: number;
  status: PlanStatus;
  reason: string;
  rationale: string;
  parent: string | null;
  created_at: string;
  confirmed_at: string | null;
  skeleton: Season;
  weeks: PlanWeek[];
  report: Report | null;
}

/** The plan does not exist (any more) or belongs to someone else. */
export interface SeasonPlanNotFound {
  kind: 'not_found';
}

export type ListSeasonPlansResult = { kind: 'ok'; plans: SeasonPlanVersion[] } | Forbidden;

export type GetSeasonPlanResult = { kind: 'ok'; plan: SeasonPlan } | SeasonPlanNotFound | Forbidden;
