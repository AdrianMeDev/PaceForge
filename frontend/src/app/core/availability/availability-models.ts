import { Forbidden, Invalid, NotFound } from '../goals/goals-models';

export type { Forbidden, Invalid, NotFound };

export type PeriodKind = 'vacation' | 'illness' | 'other';
/** Where a period stands today, by the user's own day: going on, still to come, or over. */
export type PeriodStatus = 'current' | 'upcoming' | 'past';

/**
 * The time a user can train. `weekdays` are the minutes per day, Monday first (always seven
 * numbers, 0 where nothing was entered); the weekly budget caps what they add up to and is `null`
 * for no cap; the typical week is what the user calls a normal week of training, a reference for
 * the planning after a break (`null`: not given), never a limit; the limitations are free text.
 */
export interface Availability {
  weekdays: number[];
  weekly_budget_minutes: number | null;
  typical_weekly_minutes: number | null;
  limitations: string;
}

/** What is sent to save the availability: any of the four, the rest stays as it is. */
export type AvailabilityChanges = Partial<Availability>;

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
export type DeletePeriodResult = { kind: 'deleted' } | NotFound | Forbidden;
