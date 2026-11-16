import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import { Reply, UUID, asObject, isCount, isOneOf, isUuid, toReport } from '../api/coach-replies';
import {
  Focus,
  GetSeasonPlanResult,
  GetSeasonResult,
  KeySession,
  ListSeasonPlansResult,
  PlanStatus,
  PlanWeek,
  RacePriority,
  Season,
  SeasonPhase,
  SeasonPlan,
  SeasonPlanVersion,
  SeasonRace,
  SeasonWeek,
  SessionKind,
  Sport,
} from './season-models';

const URL = `${API_BASE}/season/`;
const PLANS_URL = `${URL}plans/`;
const HANDLED_ERRORS = [401, 403, 404];
const PHASES: readonly string[] = ['base', 'build', 'specific', 'taper', 'transition'];
const PRIORITIES: readonly string[] = ['main', 'secondary', 'preparation'];
const DISCIPLINES: readonly string[] = ['running', 'cycling', 'swimming', 'triathlon'];
const SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength'];
const FOCI: readonly string[] = [
  'recovery',
  'endurance',
  'tempo',
  'threshold',
  'vo2max',
  'race_specific',
];
const KINDS: readonly string[] = [
  'long',
  'tempo',
  'threshold',
  'vo2max',
  'race_pace',
  'strength',
  'race',
];
const STATUSES: readonly string[] = ['draft', 'confirmed', 'superseded', 'discarded'];
const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;
// The most the server sends: a year of weeks.
const WEEKS_MAX = 52;
const KEY_SESSIONS_MAX = 3;
const DETAIL_MAX = 60;
const WEEK_MINUTES_MAX = 7 * 24 * 60;
const SESSION_MINUTES_MAX = 24 * 60;

/**
 * The season of the signed-in user. The skeleton is read only: the server works it out from the
 * goals, the history and the availability of the user on every request. The plans are what the
 * user's coach filled into it, one version after the other. Anything unexpected (network, other
 * server errors, an answer of the wrong shape) rejects.
 */
@Injectable({ providedIn: 'root' })
export class SeasonApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetSeasonResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', season: toSeason(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** The versions of the season plan, the newest first. */
  async plans(): Promise<ListSeasonPlansResult> {
    const reply = await this.send(this.http.get(PLANS_URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', plans: toVersions(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** One version with its weeks; a draft comes with its checks. */
  async plan(id: string): Promise<GetSeasonPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(this.http.get(`${PLANS_URL}${id}/`, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  private async send(request: Observable<HttpResponse<unknown>>): Promise<Reply> {
    try {
      const response = await firstValueFrom(request);
      return { status: response.status, body: response.body };
    } catch (error) {
      if (error instanceof HttpErrorResponse && HANDLED_ERRORS.includes(error.status)) {
        return { status: error.status, body: error.error };
      }
      throw error;
    }
  }
}

/** Only the known fields are taken over, whatever else an answer might carry. */
function toSeason(raw: unknown, reply: Reply): Season {
  const item = asObject(raw, reply);
  const { rolling, truncated, peak_minutes, weeks } = item;
  const main = item['main_race'];
  if (
    typeof rolling !== 'boolean' ||
    typeof truncated !== 'boolean' ||
    !isCount(peak_minutes) ||
    !Array.isArray(weeks) ||
    weeks.length > WEEKS_MAX ||
    // a rolling skeleton has no main race and any other has one
    rolling !== (main === null)
  ) {
    throw unexpected(reply);
  }
  return {
    rolling,
    truncated,
    main_race: main === null ? null : toRace(main, reply),
    peak_minutes,
    weeks: weeks.map((week: unknown) => toWeek(week, reply)),
  };
}

function toVersions(reply: Reply): SeasonPlanVersion[] {
  const plans = asObject(reply.body, reply)['plans'];
  if (!Array.isArray(plans)) {
    throw unexpected(reply);
  }
  return plans.map((raw: unknown) => {
    const item = asObject(raw, reply);
    const { id, version, status, reason, week_count, created_at, confirmed_at } = item;
    if (
      !isUuid(id) ||
      !isVersion(version) ||
      !isOneOf<PlanStatus>(status, STATUSES) ||
      typeof reason !== 'string' ||
      !isCount(week_count) ||
      week_count > WEEKS_MAX ||
      !isTimestamp(created_at) ||
      !isConfirmedAt(confirmed_at, status)
    ) {
      throw unexpected(reply);
    }
    return { id, version, status, reason, week_count, created_at, confirmed_at };
  });
}

/** Only the known fields are taken over; the weeks must be those of the skeleton they came with. */
function toPlan(raw: unknown, reply: Reply): SeasonPlan {
  const item = asObject(raw, reply);
  const { id, version, status, reason, rationale, parent, created_at, confirmed_at, weeks } = item;
  if (
    !isUuid(id) ||
    !isVersion(version) ||
    !isOneOf<PlanStatus>(status, STATUSES) ||
    typeof reason !== 'string' ||
    typeof rationale !== 'string' ||
    (parent !== null && !isUuid(parent)) ||
    !isTimestamp(created_at) ||
    !isConfirmedAt(confirmed_at, status) ||
    !Array.isArray(weeks) ||
    // only a draft is checked
    (status === 'draft') !== (item['report'] !== null)
  ) {
    throw unexpected(reply);
  }
  const skeleton = toSeason(item['skeleton'], reply);
  const parsed = weeks.map((week: unknown) => toPlanWeek(week, reply));
  if (
    parsed.length !== skeleton.weeks.length ||
    parsed.some((week, index) => week.week_start !== skeleton.weeks[index].week_start)
  ) {
    throw unexpected(reply);
  }
  return {
    id,
    version,
    status,
    reason,
    rationale,
    parent,
    created_at,
    confirmed_at,
    skeleton,
    weeks: parsed,
    report: item['report'] === null ? null : toReport(item['report'], reply),
  };
}

function toPlanWeek(raw: unknown, reply: Reply): PlanWeek {
  const item = asObject(raw, reply);
  const { week_start, focus, reason, total_minutes } = item;
  const minutes = asObject(item['minutes'], reply);
  const sessions = item['key_sessions'];
  const amounts = Object.entries(minutes);
  if (
    !isDate(week_start) ||
    !isOneOf<Focus>(focus, FOCI) ||
    typeof reason !== 'string' ||
    !Array.isArray(sessions) ||
    sessions.length > KEY_SESSIONS_MAX ||
    amounts.some(([sport, amount]) => !isOneOf<Sport>(sport, SPORTS) || !isCount(amount)) ||
    !isCount(total_minutes) ||
    total_minutes > WEEK_MINUTES_MAX ||
    // the total is the sum of what the week plans
    total_minutes !== amounts.reduce((sum, [, amount]) => sum + (amount as number), 0)
  ) {
    throw unexpected(reply);
  }
  const taken: Partial<Record<Sport, number>> = {};
  for (const [sport, amount] of amounts) {
    taken[sport as Sport] = amount as number;
  }
  return {
    week_start,
    minutes: taken,
    total_minutes,
    focus,
    key_sessions: sessions.map((session: unknown) => toKeySession(session, reply)),
    reason,
  };
}

function toKeySession(raw: unknown, reply: Reply): KeySession {
  const { sport, kind, minutes, detail } = asObject(raw, reply);
  if (
    !isOneOf<Sport>(sport, SPORTS) ||
    !isOneOf<SessionKind>(kind, KINDS) ||
    !isCount(minutes) ||
    minutes < 1 ||
    minutes > SESSION_MINUTES_MAX ||
    typeof detail !== 'string' ||
    detail.length > DETAIL_MAX
  ) {
    throw unexpected(reply);
  }
  return { sport, kind, minutes, detail };
}

function isVersion(value: unknown): value is number {
  return isCount(value) && value >= 1;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

/** The time of confirming is kept for a confirmed plan and for one that was replaced since. */
function isConfirmedAt(value: unknown, status: PlanStatus): value is string | null {
  return status === 'confirmed' || status === 'superseded' ? isTimestamp(value) : value === null;
}

function toWeek(raw: unknown, reply: Reply): SeasonWeek {
  const item = asObject(raw, reply);
  const { week_start, phase, recovery, target_minutes, capacity_minutes, races } = item;
  if (
    !isDate(week_start) ||
    !isOneOf<SeasonPhase>(phase, PHASES) ||
    typeof recovery !== 'boolean' ||
    !isCount(target_minutes) ||
    !isCount(capacity_minutes) ||
    target_minutes > capacity_minutes ||
    !Array.isArray(races)
  ) {
    throw unexpected(reply);
  }
  return {
    week_start,
    phase,
    recovery,
    target_minutes,
    capacity_minutes,
    races: races.map((race: unknown) => toRace(race, reply)),
  };
}

function toRace(raw: unknown, reply: Reply): SeasonRace {
  const item = asObject(raw, reply);
  const { date, priority, discipline, distance_m, title } = item;
  if (
    !isDate(date) ||
    !isOneOf<RacePriority>(priority, PRIORITIES) ||
    (discipline !== null &&
      !isOneOf<NonNullable<SeasonRace['discipline']>>(discipline, DISCIPLINES)) ||
    (distance_m !== null &&
      !(typeof distance_m === 'number' && Number.isFinite(distance_m) && distance_m > 0)) ||
    typeof title !== 'string'
  ) {
    throw unexpected(reply);
  }
  return { date, priority, discipline, distance_m, title };
}

function isDate(value: unknown): value is string {
  return typeof value === 'string' && CALENDAR_DATE.test(value);
}

function unexpected(reply: Reply): Error {
  return new Error(`The season API answered with an unexpected result (HTTP ${reply.status}).`);
}
