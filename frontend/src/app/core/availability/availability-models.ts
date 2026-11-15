import { Forbidden, Invalid, NotFound } from '../goals/goals-models';

export type { Forbidden, Invalid, NotFound };

/** The sports a plan can contain, in the order the server lists them. */
export type AvailabilitySport = 'running' | 'cycling' | 'swimming' | 'strength';

/** The parts of a day a session can be in, earliest first. */
export type AvailabilitySlot = 'morning' | 'afternoon' | 'evening';

/** How hard plans may be; each level sets the limits of the planning rules. */
export type IntensityLevel = 'relaxed' | 'normal' | 'intensive';

/**
 * The limits of the planning rules: hard days a week at most, the planned minutes in percent of
 * the reference week above which there is a warning and an error, and the share of easy minutes
 * in the endurance minutes of a week below which there is a warning.
 */
export interface Limits {
  max_hard_days: number;
  progression_warning_percent: number;
  progression_error_percent: number;
  easy_share_percent: number;
}

export type LimitName = keyof Limits;

/** The user's own limits: a number replaces the level's value, `null` keeps it. */
export type OwnLimits = Record<LimitName, number | null>;

/** Where a limitation is: a fixed list, never free text. */
export type BodyPart =
  | 'foot'
  | 'ankle'
  | 'achilles'
  | 'calf'
  | 'shin'
  | 'knee'
  | 'thigh'
  | 'hip'
  | 'back'
  | 'shoulder'
  | 'other';
/** A current limitation goes to the coach and is checked; a healed one stays as a record. */
export type LimitationStatus = 'current' | 'healed';

export type PeriodKind = 'vacation' | 'illness' | 'other';
/** Where a period stands today, by the user's own day: going on, still to come, or over. */
export type PeriodStatus = 'current' | 'upcoming' | 'past';

/**
 * The time a user can train. `weekdays` are the minutes per day, Monday first (always seven
 * numbers, 0 where nothing was entered); the weekly budget caps what they add up to and is `null`
 * for no cap; the typical week is what the user calls a normal week of training, a reference for
 * the planning after a break (`null`: not given), never a limit; `sports` are the ones the user
 * wants in a plan (at least one; all four if the user never chose); `stretching` says whether
 * stretching may be added to sessions (never as a session of its own); the limitations are free
 * text. The wishes for a week are `null` where there is none: the least to train in a week (never
 * above the budget), on how many days to train at most (1 to 7), and the weekday (0 is Monday) of
 * the long run and of the long ride. `share_limitations_text` says whether that text may go to the AI coach (off until the
 * user turns it on). `double_days` say for each weekday, Monday first, whether two sessions are allowed and
 * `time_windows` which parts of the day are open (at least one each, in the order of the day).
 * The intensity level and the own limits set the limits of the planning rules; `level_limits`
 * are the limits of every level as the server has them (read only).
 */
export interface Availability extends OwnLimits {
  weekdays: number[];
  double_days: boolean[];
  time_windows: AvailabilitySlot[][];
  weekly_budget_minutes: number | null;
  min_weekly_minutes: number | null;
  training_days: number | null;
  long_run_day: number | null;
  long_ride_day: number | null;
  typical_weekly_minutes: number | null;
  sports: AvailabilitySport[];
  stretching: boolean;
  limitations: string;
  share_limitations_text: boolean;
  intensity_level: IntensityLevel;
  level_limits: Record<IntensityLevel, Limits>;
}

/** What is sent to save the availability: any of the fields, the rest stays as it is. */
export type AvailabilityChanges = Partial<Omit<Availability, 'level_limits'>>;

/**
 * A stretch of days on which the user cannot train. Both dates belong to it (calendar dates,
 * `2027-07-12`); `days` is how many it covers.
 */
export interface Period {
  id: string;
  kind: PeriodKind;
  start_date: string;
  end_date: string;
  days: number;
  status: PeriodStatus;
  note: string;
}

/**
 * An injury or other limitation: where it is, whether it is current, and the sports it affects
 * (none: no particular sport; in the order of the sports).
 */
export interface Limitation {
  id: string;
  body_part: BodyPart;
  status: LimitationStatus;
  sports: AvailabilitySport[];
}

/** What is sent to add a limitation; the status is current when left out. */
export interface LimitationInput {
  body_part: BodyPart;
  status?: LimitationStatus;
  sports?: AvailabilitySport[];
}

/** What is sent to change a limitation: only the fields that change. */
export type LimitationChanges = Partial<LimitationInput>;

/** What is sent to add a period. */
export interface PeriodInput {
  kind: PeriodKind;
  start_date: string;
  end_date: string;
  note?: string;
}

/** What is sent to change a period: only the fields that change. */
export type PeriodChanges = Partial<PeriodInput>;

export type GetAvailabilityResult = { kind: 'ok'; availability: Availability } | Forbidden;
export type SaveAvailabilityResult =
  { kind: 'ok'; availability: Availability } | Invalid | Forbidden;
/** Going-on and coming periods first, the nearest first; then the past ones, the latest first. */
export type ListPeriodsResult = { kind: 'ok'; periods: Period[] } | Forbidden;
export type CreatePeriodResult = { kind: 'ok'; period: Period } | Invalid | Forbidden;
export type UpdatePeriodResult = { kind: 'ok'; period: Period } | Invalid | NotFound | Forbidden;
/** Current limitations first, then healed ones; the newest first within each. */
export type ListLimitationsResult = { kind: 'ok'; limitations: Limitation[] } | Forbidden;
export type CreateLimitationResult = { kind: 'ok'; limitation: Limitation } | Invalid | Forbidden;
export type UpdateLimitationResult =
  { kind: 'ok'; limitation: Limitation } | Invalid | NotFound | Forbidden;
export type DeleteLimitationResult = { kind: 'deleted' } | NotFound | Forbidden;
export type DeletePeriodResult = { kind: 'deleted' } | NotFound | Forbidden;
