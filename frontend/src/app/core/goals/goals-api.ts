import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  CreateGoalResult,
  DeleteGoalResult,
  Discipline,
  Goal,
  GoalChanges,
  GoalInput,
  GoalKind,
  GoalMetric,
  GoalPriority,
  GoalStatus,
  Invalid,
  ListGoalsResult,
  UpdateGoalResult,
} from './goals-models';

const URL = `${API_BASE}/goals/`;
const INVALID_FALLBACK = 'The input was not accepted.';
const HANDLED_ERRORS = [400, 401, 403, 404];
const KINDS: readonly string[] = ['race', 'threshold', 'general'];
const PRIORITIES: readonly string[] = ['main', 'secondary'];
const STATUSES: readonly string[] = ['active', 'achieved', 'dropped'];
const DISCIPLINES: readonly string[] = ['running', 'cycling', 'swimming', 'triathlon'];
const METRICS: readonly string[] = ['ftp', 'threshold_pace'];
const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's goals. Problems that people can act on are values; anything unexpected
 * (network, other server errors, an answer of the wrong shape) rejects.
 */
@Injectable({ providedIn: 'root' })
export class GoalsApi {
  private readonly http = inject(HttpClient);

  /** All goals, in the order the server sends them: active before finished, the main goal first. */
  async list(): Promise<ListGoalsResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', goals: toGoals(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async create(input: GoalInput): Promise<CreateGoalResult> {
    const reply = await this.send(this.http.post(URL, input, { observe: 'response' }));
    switch (reply.status) {
      case 201:
        return { kind: 'ok', goal: toGoal(reply.body, reply) };
      case 400:
        return invalid(reply);
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Changes only the fields given (for example the status). */
  async update(id: string, changes: GoalChanges): Promise<UpdateGoalResult> {
    const reply = await this.send(this.http.patch(urlOf(id), changes, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', goal: toGoal(reply.body, reply) };
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

  async delete(id: string): Promise<DeleteGoalResult> {
    const reply = await this.send(this.http.delete(urlOf(id), { observe: 'response' }));
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

function urlOf(id: string): string {
  return `${URL}${encodeURIComponent(id)}/`;
}

function toGoals(reply: Reply): Goal[] {
  if (!Array.isArray(reply.body)) {
    throw unexpected(reply);
  }
  return reply.body.map((item) => toGoal(item, reply));
}

/** Only the known fields are taken over, whatever else an answer might carry. */
function toGoal(raw: unknown, reply: Reply): Goal {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw unexpected(reply);
  }
  const item = raw as Record<string, unknown>;
  const date = item['target_date'] ?? null;
  const days = item['days_to_go'] ?? null;
  if (
    typeof item['id'] !== 'string' ||
    !isOneOf<GoalKind>(item['kind'], KINDS) ||
    typeof item['title'] !== 'string' ||
    typeof item['notes'] !== 'string' ||
    !isOneOf<GoalPriority>(item['priority'], PRIORITIES) ||
    !isOneOf<GoalStatus>(item['status'], STATUSES) ||
    (date !== null && (typeof date !== 'string' || !CALENDAR_DATE.test(date))) ||
    (days !== null && (typeof days !== 'number' || !Number.isInteger(days))) ||
    typeof item['created_at'] !== 'string' ||
    typeof item['updated_at'] !== 'string'
  ) {
    throw unexpected(reply);
  }
  return {
    id: item['id'],
    kind: item['kind'],
    title: item['title'],
    notes: item['notes'],
    priority: item['priority'],
    status: item['status'],
    target_date: date,
    discipline: optionalChoice<Discipline>(item['discipline'], DISCIPLINES, reply),
    distance_m: numberOrNull(item['distance_m'], reply),
    target_time_seconds: numberOrNull(item['target_time_seconds'], reply),
    metric: optionalChoice<GoalMetric>(item['metric'], METRICS, reply),
    target_value: numberOrNull(item['target_value'], reply),
    days_to_go: days,
    created_at: item['created_at'],
    updated_at: item['updated_at'],
  };
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

/** A missing value is `null`; anything else that is not one of the choices is the wrong shape. */
function optionalChoice<T extends string>(
  value: unknown,
  allowed: readonly string[],
  reply: Reply,
): T | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isOneOf<T>(value, allowed)) {
    throw unexpected(reply);
  }
  return value;
}

function numberOrNull(value: unknown, reply: Reply): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw unexpected(reply);
  }
  return value;
}

/**
 * DRF reports field errors as `{"title": ["…"]}` and other problems as `{"detail": "…"}` or
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
