import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import {
  ActivitySource,
  LoadSource,
  Sport as ActivitySport,
} from '../activities/activities-models';
import { API_BASE } from '../api/api-providers';
import {
  ProviderProblem,
  Sport as PlannedSport,
  WorkoutGoal,
  WorkoutSlot,
} from '../planning/planning-models';
import {
  AskCoachResult,
  CoachComment,
  CommentProblem,
  Comparison,
  CorrectResult,
  CorrectionField,
  CorrectionInput,
  FeedbackField,
  FeedbackInput,
  Figures,
  GetReviewResult,
  ListReviewWeeksResult,
  Origin,
  Recommendation,
  WeekVerdict,
  ReviewActivity,
  ReviewPlan,
  ReviewWorkout,
  ReviewableWeek,
  SaveFeedbackResult,
  SportFigures,
  WeekFeedback,
  WeekReview,
  WorkoutStatus,
} from './review-models';

const BASE = `${API_BASE}/reviews/weeks/`;
const HANDLED_ERRORS = [400, 401, 403, 404, 409, 422, 429, 502, 503];
const REJECTED_FALLBACK = 'Your entries could not be saved. Please check them.';
const PROVIDER_FALLBACK = 'The AI provider could not be used right now. Please try again later.';
const DATE = /^\d{4}-\d{2}-\d{2}$/;

const ACTIVITY_SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength', 'other'];
const PLANNED_SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength'];
const SOURCES: readonly string[] = ['fit_file', 'tcx_file', 'gpx_file', 'manual', 'intervals_icu'];
const GOALS: readonly string[] = [
  'recovery',
  'endurance',
  'tempo',
  'threshold',
  'vo2max',
  'strength',
  'other',
];
const SLOTS: readonly string[] = ['morning', 'afternoon', 'evening'];
const STATUSES: readonly WorkoutStatus[] = ['done', 'partial', 'missed', 'replaced', 'open'];
const ORIGINS: readonly string[] = ['auto', 'user'];
const RECOMMENDATIONS: readonly string[] = ['increase', 'hold', 'reduce'];
const PROVIDER_PROBLEMS: readonly string[] = [
  'invalid_key',
  'rate_limited',
  'unavailable',
  'unexpected',
  'not_allowed',
];
const CORRECTION_FIELDS: readonly CorrectionField[] = ['activity', 'no_activity', 'status'];
const FEEDBACK_FIELDS: readonly FeedbackField[] = [
  'fatigue',
  'motivation',
  'pain',
  'verdict',
  'notes',
];
const VERDICTS: readonly string[] = ['bad', 'fair', 'good', 'strong'];

interface Reply {
  status: number;
  body: unknown;
}

type Raw = Record<string, unknown>;

/**
 * The signed-in user's week reviews. Problems that people can act on are values; anything
 * unexpected (network, other server errors, an answer of the wrong shape) rejects. Only the known
 * fields are taken over and every one is checked, so that a week that arrives here is one the page
 * can show without guessing.
 */
@Injectable({ providedIn: 'root' })
export class ReviewApi {
  private readonly http = inject(HttpClient);

  /** The weeks that can be reviewed, the oldest first. */
  async weeks(): Promise<ListReviewWeeksResult> {
    const reply = await this.send(this.http.get(BASE, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', weeks: toWeeks(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** One week: `week` is its Monday, YYYY-MM-DD. Something that is no date is not even sent. */
  async week(week: string): Promise<GetReviewResult> {
    if (!DATE.test(week)) {
      return { kind: 'not_reviewable' };
    }
    const reply = await this.send(this.http.get(`${BASE}${week}/`, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', review: toReview(reply.body, reply) };
      case 404:
        return { kind: 'not_reviewable' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Sets what the user decides about one workout of the week, replacing an earlier decision;
   * an empty decision goes back to the automatic match. The server checks everything again.
   */
  async correct(week: string, workoutId: string, input: CorrectionInput): Promise<CorrectResult> {
    if (!DATE.test(week)) {
      return { kind: 'not_reviewable' };
    }
    const url = `${BASE}${week}/workouts/${encodeURIComponent(workoutId)}/`;
    const reply = await this.send(this.http.put(url, input, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', review: toReview(reply.body, reply) };
      case 400:
        return { kind: 'invalid', ...toRefusal(reply.body, CORRECTION_FIELDS) };
      case 404:
        return codeOf(reply.body) === 'workout_not_found'
          ? { kind: 'workout_not_found' }
          : { kind: 'not_reviewable' };
      case 409:
        return { kind: 'activity_taken' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Sets the feedback on the week, replacing an earlier one; nothing in it removes it. */
  async saveFeedback(week: string, input: FeedbackInput): Promise<SaveFeedbackResult> {
    if (!DATE.test(week)) {
      return { kind: 'not_reviewable' };
    }
    const reply = await this.send(
      this.http.put(`${BASE}${week}/feedback/`, input, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', review: toReview(reply.body, reply) };
      case 400:
        return { kind: 'invalid', ...toRefusal(reply.body, FEEDBACK_FIELDS) };
      case 404:
        return { kind: 'not_reviewable' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Asks the user's own coach to comment on the week that starts on `week` (a Monday,
   * YYYY-MM-DD). This takes a while: up to a minute or two. Something that is no date is not
   * even sent.
   */
  async askCoach(week: string): Promise<AskCoachResult> {
    if (!DATE.test(week)) {
      return { kind: 'not_reviewable' };
    }
    const reply = await this.send(
      this.http.post(`${BASE}${week}/comment/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 201:
        return { kind: 'ok', review: toReview(reply.body, reply) };
      case 404:
        return { kind: 'not_reviewable' };
      case 409:
        return toConflict(reply);
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

function toWeeks(reply: Reply): ReviewableWeek[] {
  const list = (reply.body as { weeks?: unknown } | null)?.weeks;
  if (!Array.isArray(list)) {
    throw unexpected(reply);
  }
  return list.map((raw) => {
    const item = object(raw, reply);
    return {
      week_start: date(item['week_start'], reply),
      has_plan: flag(item['has_plan'], reply),
      workout_count: count(item['workout_count'], reply),
      has_feedback: flag(item['has_feedback'], reply),
    };
  });
}

function toReview(body: unknown, reply: Reply): WeekReview {
  const item = object(body, reply);
  const plan = item['plan'];
  const feedback = item['feedback'];
  const comment = item['comment'];
  return {
    week_start: date(item['week_start'], reply),
    today: date(item['today'], reply),
    plan: plan === null ? null : toPlan(plan, reply),
    workouts: list(item['workouts'], reply).map((raw) => toWorkout(raw, reply)),
    activities: list(item['activities'], reply).map((raw) => toActivity(raw, reply)),
    comparison: toComparison(item['comparison'], reply),
    feedback: feedback === null ? null : toFeedback(feedback, reply),
    comment: comment === null ? null : toComment(comment, reply),
  };
}

function toPlan(raw: unknown, reply: Reply): ReviewPlan {
  const item = object(raw, reply);
  const confirmedAt = item['confirmed_at'];
  return {
    id: text(item['id'], reply),
    version: count(item['version'], reply),
    confirmed_at: confirmedAt === null ? null : text(confirmedAt, reply),
  };
}

function toWorkout(raw: unknown, reply: Reply): ReviewWorkout {
  const item = object(raw, reply);
  const slot = item['slot'];
  const activityId = item['activity_id'];
  const origin = item['activity_origin'];
  return {
    id: text(item['id'], reply),
    day: date(item['day'], reply),
    position: count(item['position'], reply),
    sport: oneOf(item['sport'], PLANNED_SPORTS, reply) as PlannedSport,
    title: string(item['title'], reply),
    goal: oneOf(item['goal'], GOALS, reply) as WorkoutGoal,
    duration_minutes: count(item['duration_minutes'], reply),
    estimated_load: count(item['estimated_load'], reply),
    slot: slot === null ? null : (oneOf(slot, SLOTS, reply) as WorkoutSlot),
    notes: string(item['notes'], reply),
    status: oneOf(item['status'], STATUSES, reply) as WorkoutStatus,
    status_origin: oneOf(item['status_origin'], ORIGINS, reply) as Origin,
    activity_id: activityId === null ? null : text(activityId, reply),
    activity_origin: origin === null ? null : (oneOf(origin, ORIGINS, reply) as Origin),
  };
}

function toActivity(raw: unknown, reply: Reply): ReviewActivity {
  const item = object(raw, reply);
  const workoutId = item['workout_id'];
  const loadSource = item['load_source'];
  return {
    id: text(item['id'], reply),
    source: oneOf(item['source'], SOURCES, reply) as ActivitySource,
    sport: oneOf(item['sport'], ACTIVITY_SPORTS, reply) as ActivitySport,
    start_time: text(item['start_time'], reply),
    day: date(item['day'], reply),
    elapsed_seconds: numberOrNull(item['elapsed_seconds'], reply),
    timer_seconds: numberOrNull(item['timer_seconds'], reply),
    distance_m: numberOrNull(item['distance_m'], reply),
    rpe: numberOrNull(item['rpe'], reply),
    notes: string(item['notes'], reply),
    load: numberOrNull(item['load'], reply),
    load_source:
      loadSource === null ? null : (oneOf(loadSource, ['intervals', 'rpe'], reply) as LoadSource),
    workout_id: workoutId === null ? null : text(workoutId, reply),
  };
}

function toComparison(raw: unknown, reply: Reply): Comparison {
  const item = object(raw, reply);
  const statuses = object(item['statuses'], reply);
  const doneShare = item['done_percent'];
  return {
    sports: list(item['sports'], reply).map((entry): SportFigures => {
      const sport = object(entry, reply);
      return {
        sport: oneOf(sport['sport'], ACTIVITY_SPORTS, reply) as ActivitySport,
        ...toFigures(sport, reply),
      };
    }),
    total: toFigures(object(item['total'], reply), reply),
    statuses: Object.fromEntries(
      STATUSES.map((status) => [status, count(statuses[status], reply)]),
    ) as Record<WorkoutStatus, number>,
    done_percent: doneShare === null ? null : count(doneShare, reply),
  };
}

function toFigures(item: Raw, reply: Reply): Figures {
  return {
    planned_count: count(item['planned_count'], reply),
    planned_minutes: count(item['planned_minutes'], reply),
    planned_load: count(item['planned_load'], reply),
    actual_count: count(item['actual_count'], reply),
    actual_minutes: count(item['actual_minutes'], reply),
    load: count(item['load'], reply),
    loaded_count: count(item['loaded_count'], reply),
    rated_count: count(item['rated_count'], reply),
  };
}

function toFeedback(raw: unknown, reply: Reply): WeekFeedback {
  const item = object(raw, reply);
  return {
    fatigue: numberOrNull(item['fatigue'], reply),
    motivation: numberOrNull(item['motivation'], reply),
    pain: numberOrNull(item['pain'], reply),
    verdict:
      item['verdict'] === null ? null : (oneOf(item['verdict'], VERDICTS, reply) as WeekVerdict),
    notes: string(item['notes'], reply),
    updated_at: text(item['updated_at'], reply),
  };
}

function toComment(raw: unknown, reply: Reply): CoachComment {
  const item = object(raw, reply);
  return {
    comment: text(item['comment'], reply),
    next_week: oneOf(item['next_week'], RECOMMENDATIONS, reply) as Recommendation,
    created_at: text(item['created_at'], reply),
  };
}

/** 409 has two reasons that the code tells apart; any other code is not an answer of this API. */
function toConflict(reply: Reply): AskCoachResult {
  switch (codeOf(reply.body)) {
    case 'nothing_to_review':
      return { kind: 'nothing_to_review' };
    case 'not_configured':
      return { kind: 'not_configured' };
    default:
      throw unexpected(reply);
  }
}

function toProblems(reply: Reply): CommentProblem[] {
  return list(object(reply.body, reply)['problems'], reply).map((raw) => {
    const item = object(raw, reply);
    return { path: string(item['path'], reply), message: text(item['message'], reply) };
  });
}

/**
 * 429 comes from two places: the provider asking to slow down (the body has a code and the
 * server's text) and this server's own limit (a plain throttling answer without a code).
 */
function toRateLimit(reply: Reply): AskCoachResult {
  const body = reply.body;
  if (typeof body === 'object' && body !== null && (body as Raw)['code']) {
    return toProviderProblem(reply, 'rate_limited');
  }
  return { kind: 'rate_limited' };
}

/**
 * The answer of the server names the problem and brings a text for users. A proxy in front of
 * the server may replace it with a page of its own: the status alone still says what kind of
 * problem it is (`fallback`) and the text is then a fixed one.
 */
function toProviderProblem(reply: Reply, fallback: ProviderProblem): AskCoachResult {
  const body =
    typeof reply.body === 'object' && reply.body !== null && !Array.isArray(reply.body)
      ? (reply.body as Raw)
      : {};
  const code = body['code'];
  const message = body['detail'];
  const retryAfter = body['retry_after'];
  const known = typeof code === 'string' && PROVIDER_PROBLEMS.includes(code);
  return {
    kind: 'provider_problem',
    problem: known ? (code as ProviderProblem) : fallback,
    message: known && typeof message === 'string' && message !== '' ? message : PROVIDER_FALLBACK,
    retry_after:
      known && typeof retryAfter === 'number' && Number.isInteger(retryAfter) && retryAfter >= 0
        ? retryAfter
        : null,
  };
}

/**
 * The messages of a refusal by field. Only the fields of the form are taken over, and only text
 * messages; an answer without any of them gives its first non-field message, or a fixed text.
 */
function toRefusal<F extends string>(
  body: unknown,
  fields: readonly F[],
): { errors: Partial<Record<F, string[]>>; message: string | null } {
  const errors: Partial<Record<F, string[]>> = {};
  const item = typeof body === 'object' && body !== null ? (body as Raw) : {};
  for (const field of fields) {
    const texts = messagesOf(item[field]);
    if (texts.length > 0) {
      errors[field] = texts;
    }
  }
  if (Object.keys(errors).length > 0) {
    return { errors, message: null };
  }
  const general = messagesOf(item['non_field_errors'])[0] ?? detailOf(body);
  return { errors, message: general ?? REJECTED_FALLBACK };
}

function messagesOf(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((m): m is string => typeof m === 'string' && m !== '')
    : [];
}

function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' && detail ? detail : null;
}

function codeOf(body: unknown): string | null {
  const code = (body as { code?: unknown } | null)?.code;
  return typeof code === 'string' ? code : null;
}

function object(value: unknown, reply: Reply): Raw {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw unexpected(reply);
  }
  return value as Raw;
}

function list(value: unknown, reply: Reply): unknown[] {
  if (!Array.isArray(value)) {
    throw unexpected(reply);
  }
  return value;
}

function string(value: unknown, reply: Reply): string {
  if (typeof value !== 'string') {
    throw unexpected(reply);
  }
  return value;
}

/** Text that must not be empty: an id or a timestamp. */
function text(value: unknown, reply: Reply): string {
  const found = string(value, reply);
  if (found === '') {
    throw unexpected(reply);
  }
  return found;
}

function date(value: unknown, reply: Reply): string {
  const found = string(value, reply);
  if (!DATE.test(found)) {
    throw unexpected(reply);
  }
  return found;
}

function flag(value: unknown, reply: Reply): boolean {
  if (typeof value !== 'boolean') {
    throw unexpected(reply);
  }
  return value;
}

/** A whole number of zero or more: a count, minutes, a load. */
function count(value: unknown, reply: Reply): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw unexpected(reply);
  }
  return value;
}

/** A missing value is `null`; anything else that is not a number is an answer of the wrong shape. */
function numberOrNull(value: unknown, reply: Reply): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw unexpected(reply);
  }
  return value;
}

function oneOf(value: unknown, allowed: readonly string[], reply: Reply): string {
  if (typeof value !== 'string' || !allowed.includes(value)) {
    throw unexpected(reply);
  }
  return value;
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
