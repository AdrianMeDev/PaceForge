import { Sport as ActivitySport } from '../activities/activities-models';
import { Forbidden, GoalKind, Rating } from '../goals/goals-models';
import { Sport as PlannedSport, ZoneSystem } from '../planning/planning-models';
import { SeasonPhase } from '../season/season-models';

export type { Forbidden };

/** The next workout: today's or a later one that is still open, else the first of next week. */
export interface NextWorkout {
  id: string;
  /** YYYY-MM-DD. */
  day: string;
  sport: PlannedSport;
  title: string;
  minutes: number;
  zone_system: ZoneSystem | null;
  zone: number | null;
  /** The workout is at Intervals.icu. */
  sent: boolean;
}

/** The current week in numbers; `average_rpe` is `null` while no activity is rated. */
export interface WeekFigures {
  planned_minutes: number;
  done_minutes: number;
  workouts_done: number;
  workouts_total: number;
  average_rpe: number | null;
}

export interface WeekGlance {
  /** The Monday, YYYY-MM-DD. */
  week_start: string;
  next_workout: NextWorkout | null;
  figures: WeekFigures;
  /** The Monday of the week to look back on and close, or `null`. */
  close_week: string | null;
}

/** The week in the confirmed season plan. */
export interface SeasonGlance {
  phase: SeasonPhase;
  recovery: boolean;
  target_minutes: number;
}

/** The active main goal; `weeks_left` is `null` without a date or once it has passed. */
export interface MainGoal {
  id: string;
  title: string;
  kind: GoalKind;
  target_date: string | null;
  weeks_left: number | null;
  rating: Rating;
}

export interface SportMinutes {
  sport: ActivitySport;
  minutes: number;
}

/** The minutes done in a week, only the sports with some. */
export interface WeekMinutes {
  week_start: string;
  sports: SportMinutes[];
}

export interface RecentActivity {
  id: string;
  day: string;
  sport: ActivitySport;
  /** `null`: the activity has no duration. */
  minutes: number | null;
}

/** The calls of the coach in the last `days` days. */
export interface CoachUsage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  days: number;
}

export interface Dashboard {
  week: WeekGlance;
  season: SeasonGlance | null;
  main_goal: MainGoal | null;
  /** The last eight weeks, the oldest first. */
  weeks: WeekMinutes[];
  /** The latest activities, the newest first. */
  recent: RecentActivity[];
  usage: CoachUsage;
}

export type GetDashboardResult = { kind: 'ok'; dashboard: Dashboard } | Forbidden;
