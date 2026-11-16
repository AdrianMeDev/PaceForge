import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import { toSeasonWeekFacts } from '../season/season-api';
import {
  Reply,
  UUID,
  asObject,
  codeOf,
  isCount,
  isOneOf,
  isTimestamp,
  isUuid,
  toFindings,
  toProblems,
  toProviderProblem,
  toRateLimit,
  toReport,
  unexpected,
} from '../api/coach-replies';
import {
  CheckPlanResult,
  ConfirmPlanResult,
  DiscardPlanResult,
  EditedPlan,
  ExportError,
  ExportStatus,
  ExportSummary,
  GenerateResult,
  GetPlanResult,
  ListWeeksResult,
  PlanStatus,
  PushOutcome,
  PushPlanResult,
  PushProblem,
  PlanVersion,
  PlannableWeek,
  RestorePlanResult,
  RevisePlanResult,
  Exercise,
  ExerciseEquipment,
  ExerciseRegion,
  Segment,
  SegmentKind,
  TargetUnit,
  Sport,
  WeekPlan,
  Workout,
  WorkoutExport,
  WorkoutGoal,
  WorkoutSlot,
  ZoneTarget,
  ZoneSystem,
} from './planning-models';

const BASE = `${API_BASE}/planning`;
const HANDLED_ERRORS = [401, 403, 404, 409, 422, 429, 502, 503];
const PUSH_FALLBACK = 'The week could not be sent to Intervals.icu. Please try again later.';

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
const TARGET_UNITS: readonly string[] = ['W', 'bpm', 's/km'];
const EXPORT_STATUSES: readonly string[] = ['not_sent', 'synced', 'failed'];
const EXPORT_ERRORS: readonly string[] = ['', 'rejected', 'unavailable', 'unexpected'];
const PUSH_PROBLEMS: readonly string[] = [
  'not_confirmed',
  'not_connected',
  'invalid_key',
  'unexpected',
];
// The zones of each zone system: the seven power levels, five heart rate zones, five pace zones.
const ZONE_COUNT: Record<string, number> = { power: 7, heart_rate: 5, pace: 5 };
const DURATION_MAX = 1440;
const STRETCHING_MAX = 60;
const REPEAT_MAX = 50;
const EXERCISES_MAX = 15;
const REGIONS: readonly string[] = ['legs', 'core', 'upper_body', 'full_body'];
const EQUIPMENT: readonly string[] = ['gym', 'dumbbells', 'bodyweight'];
const DATE = /^\d{4}-\d{2}-\d{2}$/;

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

  /**
   * Confirms a draft; the checks run again with the data of this moment. With `push` the week
   * is sent to Intervals.icu right after (only when asked for); the plan is confirmed whatever
   * the sending does, and the result says how it went.
   */
  async confirm(id: string, push = false): Promise<ConfirmPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/confirm/`, push ? { push: true } : {}, {
        observe: 'response',
      }),
    );
    switch (reply.status) {
      case 200:
        return {
          kind: 'ok',
          plan: toPlan(reply.body, reply),
          push: push ? toPush(reply.body, reply) : null,
        };
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

  /** Sends a confirmed plan to the user's Intervals.icu calendar (one call per workout). */
  async push(id: string): Promise<PushPlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/push/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', plan: toPlan(reply.body, reply), push: toPush(reply.body, reply) };
      case 404:
        return { kind: 'not_found' };
      case 409:
      case 502: {
        const code = codeOf(reply.body);
        const problem: PushProblem = isOneOf<PushProblem>(code, PUSH_PROBLEMS)
          ? code
          : reply.status === 409
            ? 'not_connected'
            : 'unexpected';
        return { kind: 'problem', problem, message: textOf(reply.body, PUSH_FALLBACK) };
      }
      case 429:
        return { kind: 'rate_limited' };
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

  /**
   * Asks for the checks of a plan that was changed by hand, for the week that starts on `week`.
   * Nothing is stored. `order[i]` says which workout of `plan` the findings call `i` (they number
   * the workouts as they are stored: by day and time of day). A week that is no date is not sent.
   */
  async check(week: string, plan: EditedPlan): Promise<CheckPlanResult> {
    if (!isDate(week)) {
      return { kind: 'not_plannable' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/weeks/${week}/check/`, toBody(plan), { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return {
          kind: 'ok',
          report: toReport(reply.body, reply),
          order: toOrder(reply.body, plan.workouts.length, reply),
        };
      case 404:
        return { kind: 'not_plannable' };
      case 422:
        return { kind: 'invalid', problems: toProblems(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Stores a plan that was changed by hand as a new draft version of the week of plan `id`, which
   * stays as it is. A draft with errors is stored too: it cannot be confirmed.
   */
  async revise(id: string, plan: EditedPlan): Promise<RevisePlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/revise/`, toBody(plan), { observe: 'response' }),
    );
    switch (reply.status) {
      case 201:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return codeOf(reply.body) === 'week_not_plannable'
          ? { kind: 'not_plannable' }
          : { kind: 'not_found' };
      case 409:
        return { kind: 'not_revisable' };
      case 422:
        return { kind: 'invalid', problems: toProblems(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Brings back a version that was replaced or discarded, as a new draft. */
  async restore(id: string): Promise<RestorePlanResult> {
    if (!UUID.test(id)) {
      return { kind: 'not_found' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}/plans/${id}/restore/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 201:
        return { kind: 'ok', plan: toPlan(reply.body, reply) };
      case 404:
        return codeOf(reply.body) === 'week_not_plannable'
          ? { kind: 'not_plannable' }
          : { kind: 'not_found' };
      case 409:
        return { kind: 'not_restorable' };
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
      season: toSeasonWeekFacts(item['season'], reply),
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
    export: toSummary(item['export'], reply),
  };
}

function toWorkout(raw: unknown, reply: Reply): Workout {
  const item = asObject(raw, reply);
  const { lineage, day, sport, title, goal, duration_minutes, notes, slot, stretching_minutes } =
    item;
  const target = toTarget(item['zone_system'], item['zone']);
  const range = toRange(item['target']);
  const sent = toExport(item['export']);
  const segments = item['segments'];
  const exercises = item['exercises'];
  if (
    !isUuid(lineage) ||
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
    sent === undefined ||
    typeof notes !== 'string' ||
    (slot !== null && !isOneOf<WorkoutSlot>(slot, SLOTS)) ||
    !isCount(stretching_minutes) ||
    stretching_minutes > STRETCHING_MAX ||
    !Array.isArray(segments) ||
    !Array.isArray(exercises) ||
    exercises.length > EXERCISES_MAX
  ) {
    throw unexpected(reply);
  }
  return {
    lineage,
    day,
    sport,
    title,
    goal,
    duration_minutes,
    ...target,
    target: range,
    export: sent,
    notes,
    slot,
    stretching_minutes,
    segments: segments.map((segment: unknown) => toSegment(segment, reply)),
    exercises: exercises.map((exercise: unknown) => toExercise(exercise, reply)),
  };
}

/**
 * What is sent of a plan that was changed by hand: only the fields of the format and the lineage.
 * Whatever else the objects carry (the `target` of a workout, its `export`) is left out on
 * purpose: the server refuses a field that is not part of the format.
 */
function toBody(plan: EditedPlan): EditedPlan {
  return {
    week_start: plan.week_start,
    rationale: plan.rationale,
    workouts: plan.workouts.map((workout) => ({
      lineage: workout.lineage,
      day: workout.day,
      sport: workout.sport,
      title: workout.title,
      goal: workout.goal,
      duration_minutes: workout.duration_minutes,
      zone_system: workout.zone_system,
      zone: workout.zone,
      notes: workout.notes,
      slot: workout.slot,
      stretching_minutes: workout.stretching_minutes,
      segments: workout.segments.map((segment) => ({
        kind: segment.kind,
        seconds: segment.seconds,
        repeat: segment.repeat,
        zone_system: segment.zone_system,
        zone: segment.zone,
      })),
      exercises: workout.exercises.map((exercise) => ({
        name: exercise.name,
        region: exercise.region,
        equipment: exercise.equipment,
        sets: exercise.sets,
        reps: exercise.reps,
        seconds: exercise.seconds,
        rpe: exercise.rpe,
        rest_seconds: exercise.rest_seconds,
      })),
    })),
  };
}

/** `order` of a check: each place of the `count` workouts sent, once. */
function toOrder(body: unknown, count: number, reply: Reply): number[] {
  const order = asObject(body, reply)['order'];
  if (
    !Array.isArray(order) ||
    order.length !== count ||
    !order.every((place): place is number => isCount(place) && place < count) ||
    new Set(order).size !== count
  ) {
    throw unexpected(reply);
  }
  return order;
}

function toExercise(raw: unknown, reply: Reply): Exercise {
  const item = asObject(raw, reply);
  const { name, region, equipment, sets, reps, seconds, rpe, rest_seconds } = item;
  if (
    typeof name !== 'string' ||
    name === '' ||
    !isOneOf<ExerciseRegion>(region, REGIONS) ||
    !isOneOf<ExerciseEquipment>(equipment, EQUIPMENT) ||
    !isCount(sets) ||
    sets < 1 ||
    !isCountOrNull(reps) ||
    !isCountOrNull(seconds) ||
    // exactly one of the two
    (reps === null) === (seconds === null) ||
    !isCountOrNull(rpe) ||
    !isCountOrNull(rest_seconds)
  ) {
    throw unexpected(reply);
  }
  return { name, region, equipment, sets, reps, seconds, rpe, rest_seconds };
}

function isCountOrNull(value: unknown): value is number | null {
  return value === null || isCount(value);
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

/** What is known about the event of a workout: `null` for a plan that is not sent. */
function toExport(raw: unknown): WorkoutExport | null | undefined {
  if (raw === null) {
    return null;
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined;
  }
  const { status, error_code, pushed_at } = raw as Record<string, unknown>;
  if (
    !isOneOf<ExportStatus>(status, EXPORT_STATUSES) ||
    !isOneOf<ExportError>(error_code, EXPORT_ERRORS) ||
    // A code goes with a failure and with nothing else.
    (error_code !== '') !== (status === 'failed') ||
    (pushed_at !== null && !isTimestamp(pushed_at)) ||
    // A workout that was never sent has no time of sending.
    (status === 'not_sent') !== (pushed_at === null)
  ) {
    return undefined;
  }
  return { status, error_code, pushed_at };
}

function toSummary(raw: unknown, reply: Reply): ExportSummary | null {
  if (raw === null) {
    return null;
  }
  const { synced, failed, not_sent, older } = asObject(raw, reply);
  if (!isCount(synced) || !isCount(failed) || !isCount(not_sent) || !isCount(older)) {
    throw unexpected(reply);
  }
  return { synced, failed, not_sent, older };
}

/** The result of a push that the answer carries. */
function toPush(body: unknown, reply: Reply): PushOutcome {
  const raw = asObject(body, reply)['push'];
  const item = asObject(raw, reply);
  if (item['ok'] === true) {
    const { synced, failed, removed, left_behind } = item;
    if (!isCount(synced) || !isCount(failed) || !isCount(removed) || !isCount(left_behind)) {
      throw unexpected(reply);
    }
    return { ok: true, synced, failed, removed, left_behind };
  }
  const { problem, message } = item;
  if (
    item['ok'] !== false ||
    !isOneOf<PushProblem>(problem, PUSH_PROBLEMS) ||
    typeof message !== 'string'
  ) {
    throw unexpected(reply);
  }
  return { ok: false, problem, message };
}

/** The `detail` of an error answer for users, or `fallback` if there is none. */
function textOf(body: unknown, fallback: string): string {
  const detail =
    typeof body === 'object' && body !== null ? (body as Record<string, unknown>)['detail'] : null;
  return typeof detail === 'string' && detail !== '' ? detail : fallback;
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
