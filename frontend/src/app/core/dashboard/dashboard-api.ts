import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { Sport as ActivitySport } from '../activities/activities-models';
import { API_BASE } from '../api/api-providers';
import { GoalKind, Rating } from '../goals/goals-models';
import { Sport as PlannedSport, ZoneSystem } from '../planning/planning-models';
import { SeasonPhase } from '../season/season-models';
import {
  CoachUsage,
  Dashboard,
  GetDashboardResult,
  MainGoal,
  NextWorkout,
  RecentActivity,
  SeasonGlance,
  SetupKey,
  SetupStep,
  SportMinutes,
  WeekFigures,
  WeekGlance,
  WeekMinutes,
  WellnessMetric,
  WellnessSummary,
  WellnessTrend,
  WellnessWarningSignal,
} from './dashboard-models';

const URL = `${API_BASE}/dashboard/`;
const HANDLED_ERRORS = [401, 403];
const DATE = /^\d{4}-\d{2}-\d{2}$/;

const ACTIVITY_SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength', 'other'];
const PLANNED_SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength'];
const ZONE_SYSTEMS: readonly string[] = ['power', 'heart_rate', 'pace'];
const PHASES: readonly string[] = ['base', 'build', 'specific', 'taper', 'transition'];
const GOAL_KINDS: readonly string[] = ['race', 'threshold', 'general'];
const SETUP_KEYS: readonly string[] = [
  'profile',
  'training_time',
  'ai_coach',
  'intervals',
  'goal',
  'activities',
  'season',
  'first_week',
];
const RATINGS: readonly string[] = ['realistic', 'ambitious', 'unrealistic', 'unknown'];
const WELLNESS_TRENDS: readonly string[] = ['up', 'down', 'flat'];
const WELLNESS_SIGNALS: readonly string[] = ['low_sleep', 'low_hrv', 'high_resting_hr'];
const WELLNESS_METRICS = ['sleep', 'hrv', 'resting_hr', 'weight'] as const;

interface Reply {
  status: number;
  body: unknown;
}

type Raw = Record<string, unknown>;

/**
 * The start page of the signed-in user in one request. Anything unexpected (network, a server
 * error, an answer of the wrong shape) rejects. Only the known fields are taken over and every
 * one is checked, so that what arrives here is something the page can show without guessing.
 */
@Injectable({ providedIn: 'root' })
export class DashboardApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetDashboardResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', dashboard: toDashboard(reply.body, reply) };
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

function toDashboard(body: unknown, reply: Reply): Dashboard {
  const item = object(body, reply);
  const season = item['season'];
  const goal = item['main_goal'];
  const wellness = item['wellness'];
  return {
    week: toWeek(item['week'], reply),
    season: season === null ? null : toSeason(season, reply),
    main_goal: goal === null ? null : toGoal(goal, reply),
    weeks: list(item['weeks'], reply).map((raw) => toWeekMinutes(raw, reply)),
    recent: list(item['recent'], reply).map((raw) => toRecent(raw, reply)),
    usage: toUsage(item['usage'], reply),
    setup: toSetup(item['setup'], reply),
    wellness: wellness === null ? null : toWellness(wellness, reply),
  };
}

function toWeek(raw: unknown, reply: Reply): WeekGlance {
  const item = object(raw, reply);
  const next = item['next_workout'];
  const close = item['close_week'];
  return {
    week_start: date(item['week_start'], reply),
    next_workout: next === null ? null : toNext(next, reply),
    figures: toFigures(item['figures'], reply),
    close_week: close === null ? null : date(close, reply),
  };
}

function toNext(raw: unknown, reply: Reply): NextWorkout {
  const item = object(raw, reply);
  const system = item['zone_system'];
  const zone = numberOrNull(item['zone'], reply);
  // The server says "no zone system" with an empty text; the models say it with `null`.
  const zone_system = system === '' || system === null ? null : oneOf(system, ZONE_SYSTEMS, reply);
  if ((zone_system === null) !== (zone === null)) {
    throw unexpected(reply);
  }
  return {
    id: text(item['id'], reply),
    day: date(item['day'], reply),
    sport: oneOf(item['sport'], PLANNED_SPORTS, reply) as PlannedSport,
    title: text(item['title'], reply),
    minutes: count(item['minutes'], reply),
    zone_system: zone_system as ZoneSystem | null,
    zone,
    sent: flag(item['sent'], reply),
  };
}

function toFigures(raw: unknown, reply: Reply): WeekFigures {
  const item = object(raw, reply);
  return {
    planned_minutes: count(item['planned_minutes'], reply),
    done_minutes: count(item['done_minutes'], reply),
    workouts_done: count(item['workouts_done'], reply),
    workouts_total: count(item['workouts_total'], reply),
    average_rpe: numberOrNull(item['average_rpe'], reply),
  };
}

function toSeason(raw: unknown, reply: Reply): SeasonGlance {
  const item = object(raw, reply);
  return {
    phase: oneOf(item['phase'], PHASES, reply) as SeasonPhase,
    recovery: flag(item['recovery'], reply),
    target_minutes: count(item['target_minutes'], reply),
  };
}

function toGoal(raw: unknown, reply: Reply): MainGoal {
  const item = object(raw, reply);
  const targetDate = item['target_date'];
  const weeks = numberOrNull(item['weeks_left'], reply);
  if (weeks !== null && (!Number.isInteger(weeks) || weeks < 0)) {
    throw unexpected(reply);
  }
  return {
    id: text(item['id'], reply),
    title: text(item['title'], reply),
    kind: oneOf(item['kind'], GOAL_KINDS, reply) as GoalKind,
    target_date: targetDate === null ? null : date(targetDate, reply),
    weeks_left: weeks,
    // Only the rating is shown; the page for the goals has the rest of the judgement.
    rating: oneOf(object(item['assessment'], reply)['rating'], RATINGS, reply) as Rating,
  };
}

function toWeekMinutes(raw: unknown, reply: Reply): WeekMinutes {
  const item = object(raw, reply);
  return {
    week_start: date(item['week_start'], reply),
    sports: list(item['sports'], reply).map((entry): SportMinutes => {
      const sport = object(entry, reply);
      return {
        sport: oneOf(sport['sport'], ACTIVITY_SPORTS, reply) as ActivitySport,
        minutes: count(sport['minutes'], reply),
      };
    }),
  };
}

function toRecent(raw: unknown, reply: Reply): RecentActivity {
  const item = object(raw, reply);
  const minutes = item['minutes'];
  return {
    id: text(item['id'], reply),
    day: date(item['day'], reply),
    sport: oneOf(item['sport'], ACTIVITY_SPORTS, reply) as ActivitySport,
    minutes: minutes === null ? null : count(minutes, reply),
  };
}

function toUsage(raw: unknown, reply: Reply): CoachUsage {
  const item = object(raw, reply);
  return {
    calls: count(item['calls'], reply),
    input_tokens: count(item['input_tokens'], reply),
    output_tokens: count(item['output_tokens'], reply),
    days: count(item['days'], reply),
  };
}

function toSetup(raw: unknown, reply: Reply): SetupStep[] {
  const item = object(raw, reply);
  return list(item['steps'], reply).map((entry) => {
    const step = object(entry, reply);
    return {
      key: oneOf(step['key'], SETUP_KEYS, reply) as SetupKey,
      done: flag(step['done'], reply),
      optional: flag(step['optional'], reply),
    };
  });
}

function toWellness(raw: unknown, reply: Reply): WellnessSummary {
  const item = object(raw, reply);
  const result = {} as Record<(typeof WELLNESS_METRICS)[number], WellnessMetric>;
  for (const name of WELLNESS_METRICS) {
    result[name] = toWellnessMetric(item[name], reply);
  }
  return {
    sleep: result.sleep,
    hrv: result.hrv,
    resting_hr: result.resting_hr,
    weight: result.weight,
    warning: flag(item['warning'], reply),
    warning_signals: list(item['warning_signals'], reply).map(
      (entry) => oneOf(entry, WELLNESS_SIGNALS, reply) as WellnessWarningSignal,
    ),
  };
}

function toWellnessMetric(raw: unknown, reply: Reply): WellnessMetric {
  const item = object(raw, reply);
  const recent = metricNumber(item['recent'], reply);
  const baseline = metricNumber(item['baseline'], reply);
  const trend = item['trend'];
  if ((recent === null) !== (baseline === null)) {
    throw unexpected(reply);
  }
  const parsedTrend =
    trend === null ? null : (oneOf(trend, WELLNESS_TRENDS, reply) as WellnessTrend);
  if ((recent === null) !== (parsedTrend === null)) {
    throw unexpected(reply);
  }
  return { recent, baseline, trend: parsedTrend };
}

/** A measurement (a mean) is `null` when there were too few readings; nothing else is accepted. */
function metricNumber(value: unknown, reply: Reply): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw unexpected(reply);
  }
  return value;
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

/** Text that must not be empty: an id or a title. */
function text(value: unknown, reply: Reply): string {
  if (typeof value !== 'string' || value === '') {
    throw unexpected(reply);
  }
  return value;
}

function date(value: unknown, reply: Reply): string {
  if (typeof value !== 'string' || !DATE.test(value)) {
    throw unexpected(reply);
  }
  return value;
}

function flag(value: unknown, reply: Reply): boolean {
  if (typeof value !== 'boolean') {
    throw unexpected(reply);
  }
  return value;
}

/** A whole number of zero or more: a count or minutes. */
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
