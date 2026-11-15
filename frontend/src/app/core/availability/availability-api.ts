import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  Availability,
  AvailabilityChanges,
  AvailabilitySlot,
  AvailabilitySport,
  CreatePeriodResult,
  DeletePeriodResult,
  GetAvailabilityResult,
  IntensityLevel,
  Invalid,
  LimitName,
  Limits,
  ListPeriodsResult,
  Period,
  PeriodChanges,
  PeriodInput,
  PeriodKind,
  PeriodStatus,
  SaveAvailabilityResult,
  UpdatePeriodResult,
} from './availability-models';

const URL = `${API_BASE}/availability/`;
const PERIODS_URL = `${URL}periods/`;
const INVALID_FALLBACK = 'The input was not accepted.';
const HANDLED_ERRORS = [400, 401, 403, 404];
const KINDS: readonly string[] = ['vacation', 'illness', 'other'];
const SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength'];
const SLOTS: readonly string[] = ['morning', 'afternoon', 'evening'];
const STATUSES: readonly string[] = ['current', 'upcoming', 'past'];
const LEVELS: readonly IntensityLevel[] = ['relaxed', 'normal', 'intensive'];
const LIMIT_NAMES: readonly LimitName[] = [
  'max_hard_days',
  'progression_warning_percent',
  'progression_error_percent',
  'easy_share_percent',
];
const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's training time and periods of absence. Problems that people can act on are
 * values; anything unexpected (network, other server errors, an answer of the wrong shape)
 * rejects.
 */
@Injectable({ providedIn: 'root' })
export class AvailabilityApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetAvailabilityResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', availability: toAvailability(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Saves the fields given; the answer is the whole availability as it is now. */
  async save(changes: AvailabilityChanges): Promise<SaveAvailabilityResult> {
    const reply = await this.send(this.http.patch(URL, changes, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', availability: toAvailability(reply.body, reply) };
      case 400:
        return invalid(reply);
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** All periods, in the order the server sends them. */
  async listPeriods(): Promise<ListPeriodsResult> {
    const reply = await this.send(this.http.get(PERIODS_URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', periods: toPeriods(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async createPeriod(input: PeriodInput): Promise<CreatePeriodResult> {
    const reply = await this.send(this.http.post(PERIODS_URL, input, { observe: 'response' }));
    switch (reply.status) {
      case 201:
        return { kind: 'ok', period: toPeriod(reply.body, reply) };
      case 400:
        return invalid(reply);
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Changes only the fields given. */
  async updatePeriod(id: string, changes: PeriodChanges): Promise<UpdatePeriodResult> {
    const reply = await this.send(this.http.patch(periodUrl(id), changes, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', period: toPeriod(reply.body, reply) };
      case 400:
        return invalid(reply);
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async deletePeriod(id: string): Promise<DeletePeriodResult> {
    const reply = await this.send(this.http.delete(periodUrl(id), { observe: 'response' }));
    switch (reply.status) {
      case 204:
        return { kind: 'deleted' };
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

function periodUrl(id: string): string {
  return `${PERIODS_URL}${encodeURIComponent(id)}/`;
}

/** Only the known fields are taken over, whatever else an answer might carry. */
function toAvailability(raw: unknown, reply: Reply): Availability {
  const item = asObject(raw, reply);
  const budget = item['weekly_budget_minutes'];
  const typical = item['typical_weekly_minutes'];
  const sports = item['sports'];
  const weekdays = item['weekdays'];
  const doubleDays = item['double_days'];
  const windows = item['time_windows'];
  if (
    !Array.isArray(weekdays) ||
    weekdays.length !== 7 ||
    !weekdays.every(isMinutes) ||
    !Array.isArray(doubleDays) ||
    doubleDays.length !== 7 ||
    !doubleDays.every((flag) => typeof flag === 'boolean') ||
    !Array.isArray(windows) ||
    windows.length !== 7 ||
    !windows.every(isTimeWindow) ||
    (budget !== null && !isMinutes(budget)) ||
    (typical !== null && !isMinutes(typical)) ||
    // At least one sport, each of the known ones once.
    !Array.isArray(sports) ||
    sports.length === 0 ||
    !sports.every((sport) => isOneOf<AvailabilitySport>(sport, SPORTS)) ||
    new Set(sports).size !== sports.length ||
    typeof item['stretching'] !== 'boolean' ||
    typeof item['limitations'] !== 'string' ||
    !isOneOf<IntensityLevel>(item['intensity_level'], LEVELS) ||
    !LIMIT_NAMES.every((name) => item[name] === null || isWholeNumber(item[name]))
  ) {
    throw unexpected(reply);
  }
  const levelLimits = asObject(item['level_limits'], reply);
  return {
    weekdays: [...(weekdays as number[])],
    double_days: [...(doubleDays as boolean[])],
    time_windows: (windows as AvailabilitySlot[][]).map((day) => [...day]),
    weekly_budget_minutes: budget,
    typical_weekly_minutes: typical,
    sports: [...(sports as AvailabilitySport[])],
    stretching: item['stretching'],
    limitations: item['limitations'],
    intensity_level: item['intensity_level'],
    max_hard_days: item['max_hard_days'] as number | null,
    progression_warning_percent: item['progression_warning_percent'] as number | null,
    progression_error_percent: item['progression_error_percent'] as number | null,
    easy_share_percent: item['easy_share_percent'] as number | null,
    level_limits: {
      relaxed: toLimits(levelLimits['relaxed'], reply),
      normal: toLimits(levelLimits['normal'], reply),
      intensive: toLimits(levelLimits['intensive'], reply),
    },
  };
}

/** The four limits of a level, each a whole number. */
function toLimits(raw: unknown, reply: Reply): Limits {
  const item = asObject(raw, reply);
  if (!LIMIT_NAMES.every((name) => isWholeNumber(item[name]))) {
    throw unexpected(reply);
  }
  return {
    max_hard_days: item['max_hard_days'] as number,
    progression_warning_percent: item['progression_warning_percent'] as number,
    progression_error_percent: item['progression_error_percent'] as number,
    easy_share_percent: item['easy_share_percent'] as number,
  };
}

function toPeriods(reply: Reply): Period[] {
  if (!Array.isArray(reply.body)) {
    throw unexpected(reply);
  }
  return reply.body.map((item) => toPeriod(item, reply));
}

function toPeriod(raw: unknown, reply: Reply): Period {
  const item = asObject(raw, reply);
  const days = item['days'];
  if (
    typeof item['id'] !== 'string' ||
    !isOneOf<PeriodKind>(item['kind'], KINDS) ||
    !isCalendarDate(item['start_date']) ||
    !isCalendarDate(item['end_date']) ||
    typeof days !== 'number' ||
    !Number.isInteger(days) ||
    days < 1 ||
    !isOneOf<PeriodStatus>(item['status'], STATUSES) ||
    typeof item['note'] !== 'string'
  ) {
    throw unexpected(reply);
  }
  return {
    id: item['id'],
    kind: item['kind'],
    start_date: item['start_date'],
    end_date: item['end_date'],
    days,
    status: item['status'],
    note: item['note'],
  };
}

function asObject(raw: unknown, reply: Reply): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw unexpected(reply);
  }
  return raw as Record<string, unknown>;
}

/** At least one part of the day, each of the known ones at most once. */
function isTimeWindow(value: unknown): value is AvailabilitySlot[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((slot) => isOneOf<AvailabilitySlot>(slot, SLOTS)) &&
    new Set(value).size === value.length
  );
}

function isMinutes(value: unknown): value is number {
  return isWholeNumber(value);
}

function isWholeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isCalendarDate(value: unknown): value is string {
  return typeof value === 'string' && CALENDAR_DATE.test(value);
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

/**
 * DRF reports field errors as `{"weekdays": ["…"]}` and other problems as `{"detail": "…"}` or
 * `{"non_field_errors": ["…"]}`. All messages are kept, by field and as one list.
 */
function invalid(reply: Reply): Invalid {
  const fields: Record<string, string[]> = {};
  if (typeof reply.body === 'object' && reply.body !== null && !Array.isArray(reply.body)) {
    for (const [name, value] of Object.entries(reply.body)) {
      const messages = [value].flat().filter((text): text is string => typeof text === 'string');
      if (messages.length) {
        fields[name] = messages;
      }
    }
  }
  const errors = Object.values(fields).flat();
  return { kind: 'invalid', errors: errors.length ? errors : [INVALID_FALLBACK], fields };
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
