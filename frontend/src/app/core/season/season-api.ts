import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  GetSeasonResult,
  RacePriority,
  Season,
  SeasonPhase,
  SeasonRace,
  SeasonWeek,
} from './season-models';

const URL = `${API_BASE}/season/`;
const HANDLED_ERRORS = [401, 403];
const PHASES: readonly string[] = ['base', 'build', 'specific', 'taper', 'transition'];
const PRIORITIES: readonly string[] = ['main', 'secondary', 'preparation'];
const DISCIPLINES: readonly string[] = ['running', 'cycling', 'swimming', 'triathlon'];
const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;
// The most the server sends: a year of weeks.
const WEEKS_MAX = 52;

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The skeleton of the signed-in user's season. It is read only: the server works it out from the
 * goals, the history and the availability of the user on every request. Anything unexpected
 * (network, other server errors, an answer of the wrong shape) rejects.
 */
@Injectable({ providedIn: 'root' })
export class SeasonApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetSeasonResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', season: toSeason(reply) };
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
function toSeason(reply: Reply): Season {
  const item = asObject(reply.body, reply);
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

function asObject(value: unknown, reply: Reply): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw unexpected(reply);
  }
  return value as Record<string, unknown>;
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isDate(value: unknown): value is string {
  return typeof value === 'string' && CALENDAR_DATE.test(value);
}

function unexpected(reply: Reply): Error {
  return new Error(`The season API answered with an unexpected result (HTTP ${reply.status}).`);
}
