import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  ConfirmPlanResult,
  DiscardPlanResult,
  Finding,
  GenerateResult,
  GetPlanResult,
  ListWeeksResult,
  PlanProblem,
  PlanStatus,
  PlanVersion,
  PlannableWeek,
  ProviderProblem,
  Report,
  Segment,
  SegmentKind,
  TargetUnit,
  Severity,
  Sport,
  WeekPlan,
  Workout,
  WorkoutGoal,
  WorkoutSlot,
  ZoneTarget,
  ZoneSystem,
} from './planning-models';

const BASE = `${API_BASE}/planning`;
const HANDLED_ERRORS = [401, 403, 404, 409, 422, 429, 502, 503];
const FALLBACK_TEXT = 'The AI provider could not be used right now. Please try again later.';

const SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength'];
const GOALS: readonly string[] = [
  'recovery',
  'endurance',
  'tempo',
  'threshold',
  'vo2max',
  'strength',
  'other',
];
const ZONE_SYSTEMS: readonly string[] = ['power', 'heart_rate', 'pace'];
const SEGMENT_KINDS: readonly string[] = ['warmup', 'steady', 'work', 'recovery', 'cooldown'];
const SLOTS: readonly string[] = ['morning', 'afternoon', 'evening'];
const STATUSES: readonly string[] = ['draft', 'confirmed', 'superseded', 'discarded'];
const SEVERITIES: readonly string[] = ['error', 'warning'];
const PROBLEMS: readonly string[] = [
  'invalid_key',
  'rate_limited',
  'unavailable',
  'unexpected',
  'not_allowed',
];
const TARGET_UNITS: readonly string[] = ['W', 'bpm', 's/km'];
// The zones of each zone system: the seven power levels, five heart rate zones, five pace zones.
const ZONE_COUNT: Record<string, number> = { power: 7, heart_rate: 5, pace: 5 };
const DURATION_MAX = 1440;
const STRETCHING_MAX = 60;
const REPEAT_MAX = 50;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's week plans. Problems that people can act on are values; anything
 * unexpected (network, other server errors, an answer of the wrong shape) rejects. Nothing is
 * taken over from an answer but the known fields, and every field is checked, so that a plan
 * that arrives here is one the page can show without guessing.
 */
@Injectable({ providedIn: 'root' })
export class PlanningApi {
  private readonly http = inject(HttpClient);

  /** The weeks that can be planned, each with the versions that exist of it. */
  async weeks(): Promise<ListWeeksResult> {
    const reply = await this.send(this.http.get(`${BASE}/weeks/`, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', weeks: toWeeks(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Asks the user's own coach for a draft of the week that starts on `week` (a Monday,
   * YYYY-MM-DD). This takes a while: up to a minute or two. A week that is no date is not
   * sent at all.
   */
  async generate(week: string): Promise<GenerateResult> {
    if (!isDate(week)) {
      return { kind: 'not_plannable' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/weeks/${week}/generate/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 201:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return { kind: 'not_plannable' };
      case 409:
        // Two reasons share the status; the code tells them apart. Anything else (a proxy's page,
        // an answer of another shape) keeps meaning what 409 meant before: no provider.
        return codeOf(reply.body) === 'no_time' ? { kind: 'no_time' } : { kind: 'not_configured' };
      case 422:
        return { kind: 'not_usable', problems: toProblems(reply) };
      case 429:
        return toRateLimit(reply);
      case 502:
        return toProviderProblem(reply, 'unexpected');
      case 503:
        return toProviderProblem(reply, 'unavailable');
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** One plan with its workouts; a draft comes with its checks. */
  async get(id: string): Promise<GetPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(this.http.get(`${BASE}/plans/${id}/`, { observe: 'response' }));
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

  /** Confirms a draft; the checks run again with the data of this moment. */
  async confirm(id: string): Promise<ConfirmPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/confirm/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return { kind: 'not_found' };
      case 409:
        return { kind: 'not_a_draft' };
      case 422:
        return {
          kind: 'not_confirmable',
          findings: toFindings(asObject(reply.body, reply), reply),
        };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Throws a draft away. */
  async discard(id: string): Promise<DiscardPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/discard/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return { kind: 'not_found' };
      case 409:
        return { kind: 'not_a_draft' };
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

function toWeeks(raw: unknown, reply: Reply): PlannableWeek[] {
  const weeks = asObject(raw, reply)['weeks'];
  if (!Array.isArray(weeks)) {
    throw unexpected(reply);
  }
  return weeks.map((raw: unknown) => {
    const item = asObject(raw, reply);
    const plans = item['plans'];
    if (!isMonday(item['week_start']) || !Array.isArray(plans)) {
      throw unexpected(reply);
    }
    return {
      week_start: item['week_start'],
      plans: plans.map((plan: unknown) => toVersion(plan, reply)),
    };
  });
}

function toVersion(raw: unknown, reply: Reply): PlanVersion {
  const item = asObject(raw, reply);
  const { id, version, status, reason, workout_count, created_at, confirmed_at } = item;
  if (
    !isUuid(id) ||
    !isCount(version) ||
    version < 1 ||
    !isOneOf<PlanStatus>(status, STATUSES) ||
    typeof reason !== 'string' ||
    !isCount(workout_count) ||
    !isTimestamp(created_at) ||
    !isConfirmedAt(confirmed_at, status)
  ) {
    throw unexpected(reply);
  }
  return { id, version, status, reason, workout_count, created_at, confirmed_at };
}

function toPlan(raw: unknown, reply: Reply): WeekPlan {
  const item = asObject(raw, reply);
  const { id, week_start, version, status, reason, rationale, parent, created_at } = item;
  const workouts = item['workouts'];
  const confirmedAt = item['confirmed_at'];
  if (
    !isUuid(id) ||
    !isMonday(week_start) ||
    !isCount(version) ||
    version < 1 ||
    !isOneOf<PlanStatus>(status, STATUSES) ||
    typeof reason !== 'string' ||
    typeof rationale !== 'string' ||
    (parent !== null && !isUuid(parent)) ||
    !isTimestamp(created_at) ||
    !isConfirmedAt(confirmedAt, status) ||
    !Array.isArray(workouts) ||
    // Only a draft is checked: the report is there exactly for drafts.
    (status === 'draft') !== (item['report'] !== null && item['report'] !== undefined)
  ) {
    throw unexpected(reply);
  }
  return {
    id,
    week_start,
    version,
    status,
    reason,
    rationale,
    parent,
    created_at,
    confirmed_at: confirmedAt,
    workouts: workouts.map((workout: unknown) => toWorkout(workout, reply)),
    report: status === 'draft' ? toReport(item['report'], reply) : null,
  };
}

function toWorkout(raw: unknown, reply: Reply): Workout {
  const item = asObject(raw, reply);
  const { day, sport, title, goal, duration_minutes, notes, slot, stretching_minutes } = item;
  const target = toTarget(item['zone_system'], item['zone']);
  const range = toRange(item['target']);
  const segments = item['segments'];
  if (
    !isDate(day) ||
    !isOneOf<Sport>(sport, SPORTS) ||
    typeof title !== 'string' ||
    title === '' ||
    !isOneOf<WorkoutGoal>(goal, GOALS) ||
    !isCount(duration_minutes) ||
    duration_minutes < 1 ||
    duration_minutes > DURATION_MAX ||
    target === null ||
    range === undefined ||
    typeof notes !== 'string' ||
    (slot !== null && !isOneOf<WorkoutSlot>(slot, SLOTS)) ||
    !isCount(stretching_minutes) ||
    stretching_minutes > STRETCHING_MAX ||
    !Array.isArray(segments)
  ) {
    throw unexpected(reply);
  }
  return {
    day,
    sport,
    title,
    goal,
    duration_minutes,
    ...target,
    target: range,
    notes,
    slot,
    stretching_minutes,
    segments: segments.map((segment: unknown) => toSegment(segment, reply)),
  };
}

function toSegment(raw: unknown, reply: Reply): Segment {
  const item = asObject(raw, reply);
  const { kind, seconds, repeat } = item;
  const target = toTarget(item['zone_system'], item['zone']);
  const range = toRange(item['target']);
  if (
    !isOneOf<SegmentKind>(kind, SEGMENT_KINDS) ||
    !isCount(seconds) ||
    seconds < 1 ||
    !isCount(repeat) ||
    repeat < 1 ||
    repeat > REPEAT_MAX ||
    target === null ||
    range === undefined
  ) {
    throw unexpected(reply);
  }
  return { kind, seconds, repeat, ...target, target: range };
}

function toReport(raw: unknown, reply: Reply): Report {
  const item = asObject(raw, reply);
  const findings = toFindings(item, reply);
  // A plan is valid exactly when none of the findings is an error.
  if (
    typeof item['valid'] !== 'boolean' ||
    item['valid'] !== findings.every((finding) => finding.severity !== 'error')
  ) {
    throw unexpected(reply);
  }
  return { valid: item['valid'], findings };
}

function toFindings(item: Record<string, unknown>, reply: Reply): Finding[] {
  const findings = item['findings'];
  if (!Array.isArray(findings)) {
    throw unexpected(reply);
  }
  return findings.map((raw: unknown) => {
    const finding = asObject(raw, reply);
    const { severity, code, message, path } = finding;
    if (
      !isOneOf<Severity>(severity, SEVERITIES) ||
      typeof code !== 'string' ||
      typeof message !== 'string' ||
      typeof path !== 'string'
    ) {
      throw unexpected(reply);
    }
    return { severity, code, message, path };
  });
}

/** The `code` of an error answer, `null` if the body is no object with a text there. */
function codeOf(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return null;
  }
  const code = (body as Record<string, unknown>)['code'];
  return typeof code === 'string' ? code : null;
}

function toProblems(reply: Reply): PlanProblem[] {
  const problems = asObject(reply.body, reply)['problems'];
  if (!Array.isArray(problems)) {
    throw unexpected(reply);
  }
  return problems.map((raw: unknown) => {
    const { path, message } = asObject(raw, reply);
    if (typeof path !== 'string' || typeof message !== 'string') {
      throw unexpected(reply);
    }
    return { path, message };
  });
}

/**
 * 429 comes from two places: the provider asking to slow down (the body has a code and the
 * server's text) and this server's own limit (a plain throttling answer without a code).
 */
function toRateLimit(reply: Reply): GenerateResult {
  const body = reply.body;
  if (typeof body === 'object' && body !== null && (body as Record<string, unknown>)['code']) {
    return toProviderProblem(reply, 'rate_limited');
  }
  return { kind: 'rate_limited' };
}

/**
 * The answer of the server names the problem and brings a text for users. A proxy in front of
 * the server may replace it with a page of its own: the status alone still says what kind of
 * problem it is (`fallback`) and the text is then a fixed one.
 */
function toProviderProblem(reply: Reply, fallback: ProviderProblem): GenerateResult {
  const body =
    typeof reply.body === 'object' && reply.body !== null && !Array.isArray(reply.body)
      ? (reply.body as Record<string, unknown>)
      : {};
  const code = body['code'];
  const message = body['detail'];
  const retryAfter = body['retry_after'];
  const known = isOneOf<ProviderProblem>(code, PROBLEMS);
  return {
    kind: 'provider_problem',
    problem: known ? code : fallback,
    message: known && typeof message === 'string' && message !== '' ? message : FALLBACK_TEXT,
    retry_after: known && isCount(retryAfter) ? retryAfter : null,
  };
}

/** The target of a workout or a segment: a zone system with a zone of it, or neither. */
function toTarget(
  system: unknown,
  zone: unknown,
): { zone_system: ZoneSystem | null; zone: number | null } | null {
  if (system === null || zone === null) {
    return system === null && zone === null ? { zone_system: null, zone: null } : null;
  }
  if (
    isOneOf<ZoneSystem>(system, ZONE_SYSTEMS) &&
    isCount(zone) &&
    zone >= 1 &&
    zone <= ZONE_COUNT[system]
  ) {
    return { zone_system: system, zone };
  }
  return null;
}

/** The range of a zone, `null` for none, `undefined` for something that is no range. */
function toRange(raw: unknown): ZoneTarget | null | undefined {
  if (raw === null) {
    return null;
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined;
  }
  const { low, high, unit } = raw as Record<string, unknown>;
  if (!isCount(low) || !isCount(high) || low > high || !isOneOf<TargetUnit>(unit, TARGET_UNITS)) {
    return undefined;
  }
  return { low, high, unit };
}

function isConfirmedAt(value: unknown, status: PlanStatus): value is string | null {
  // The time of confirming is kept for a confirmed plan and for one that was replaced since.
  return status === 'confirmed' || status === 'superseded' ? isTimestamp(value) : value === null;
}

function asObject(raw: unknown, reply: Reply): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw unexpected(reply);
  }
  return raw as Record<string, unknown>;
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

function isDate(value: unknown): value is string {
  if (typeof value !== 'string' || !DATE.test(value)) {
    return false;
  }
  const time = Date.parse(`${value}T00:00:00Z`);
  // A date that does not exist (February 30th) comes back as another one.
  return !Number.isNaN(time) && new Date(time).toISOString().startsWith(value);
}

function isMonday(value: unknown): value is string {
  return isDate(value) && new Date(`${value}T00:00:00Z`).getUTCDay() === 1;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
