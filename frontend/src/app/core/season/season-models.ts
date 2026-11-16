import { Forbidden, Invalid } from '../goals/goals-models';
import { ProviderProblemResult } from '../api/coach-replies';
import {
  Finding,
  PlanProblem,
  PlanStatus,
  RateLimited,
  Report,
  Sport,
} from '../planning/planning-models';

export type { Forbidden, Invalid, PlanProblem, PlanStatus, RateLimited, Report, Sport };

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
  /**
   * The minutes the athlete trained in the week, by sport (`other`: activities of no sport of the
   * plan), only the sports with minutes. `null`: not known, which is every week of every version
   * but the confirmed one and its weeks that have not begun; `[]`: a week without any training.
   */
  done: DoneMinutes[] | null;
  minutes: Partial<Record<Sport, number>>;
  total_minutes: number;
  focus: Focus;
  key_sessions: KeySession[];
  reason: string;
}

/** The minutes done in one sport; `other` is no sport of the plan. */
export interface DoneMinutes {
  sport: Sport | 'other';
  minutes: number;
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
  /** What the athlete asked for if the coach made this version of another one; their own text. */
  request: string;
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

/** Only a draft can be confirmed or discarded. */
export interface SeasonPlanNotADraft {
  kind: 'not_a_draft';
}

export type GenerateSeasonResult =
  /** A draft was stored (version 1 or newer); its checks may still have errors. */
  | { kind: 'ok'; plan: SeasonPlan }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** No week of the season offers any training time; nothing was asked of the coach. */
  | { kind: 'no_time' }
  /** The coach gave no readable plan, even after being told what was wrong. */
  | { kind: 'not_usable'; problems: PlanProblem[] }
  /** The provider refused or could not be reached; `message` is the server's text for users. */
  | ProviderProblemResult
  /** Too many seasons requested in a short time (this server's limit, not the provider's). */
  | RateLimited
  | Forbidden;

export type ConfirmSeasonResult =
  | { kind: 'ok'; plan: SeasonPlan }
  | SeasonPlanNotFound
  | SeasonPlanNotADraft
  /** The plan has errors; `findings` has all checks, the errors among them. */
  | { kind: 'not_confirmable'; findings: Finding[] }
  | Forbidden;

export type ChangeSeasonResult =
  /** The new draft, with its checks; the version it was made from is not touched. */
  | { kind: 'ok'; plan: SeasonPlan }
  /** The request is missing, empty, too long or not plain text; `fields.request` says what. */
  | Invalid
  | SeasonPlanNotFound
  /** Only the confirmed version and a draft can be changed. */
  | { kind: 'not_changeable' }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** The coach gave the season back as it was; nothing was stored. */
  | { kind: 'unchanged' }
  /** The coach gave no readable plan, even after being told what was wrong. */
  | { kind: 'not_usable'; problems: PlanProblem[] }
  | ProviderProblemResult
  | RateLimited
  | Forbidden;

export type RestoreSeasonResult =
  /** The new draft, with its checks as they are now; the version it was made from is not touched. */
  | { kind: 'ok'; plan: SeasonPlan }
  | SeasonPlanNotFound
  /** Only a version that was replaced or discarded can be restored. */
  | { kind: 'not_restorable' }
  | Forbidden;

export type DiscardSeasonResult =
  { kind: 'ok'; plan: SeasonPlan } | SeasonPlanNotFound | SeasonPlanNotADraft | Forbidden;

/**
 * What the confirmed season plan says about one week, as the week plan page gets it: the phase
 * and the aim of the skeleton and what the coach filled in. `reason` and the details of the key
 * sessions are the coach's own words, shown as text only. `minutes` has one entry per sport that
 * has minutes; `total_minutes` is their sum.
 */
export interface SeasonWeekFacts {
  phase: SeasonPhase;
  recovery: boolean;
  target_minutes: number;
  minutes: { sport: Sport; minutes: number }[];
  total_minutes: number;
  focus: Focus;
  key_sessions: KeySession[];
  reason: string;
  /** The races of the week, by day and priority (the titles are in the goals). */
  races: { date: string; priority: RacePriority }[];
}
