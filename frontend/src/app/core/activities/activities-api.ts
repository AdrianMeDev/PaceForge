import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  Activity,
  ActivityDetail,
  ActivityPage,
  ActivitySource,
  DeleteActivityResult,
  EnterActivityResult,
  GetActivityResult,
  ImportActivityResult,
  Lap,
  ListActivitiesResult,
  ManualActivityInput,
  ManualField,
  RateActivityResult,
  RatingField,
  RatingInput,
  Sport,
  SyncActivitiesResult,
  Unavailable,
} from './activities-models';

const URL = `${API_BASE}/activities/`;
const IMPORT_URL = `${URL}import/`;
const MANUAL_URL = `${URL}manual/`;
const SYNC_URL = `${URL}sync/`;
const REJECTED_FALLBACK = 'The file could not be imported.';
const REJECTED_MANUAL = 'The session could not be saved. Please check your entries.';
const REJECTED_RATING = 'The rating could not be saved. Please check your entries.';
const UNAVAILABLE_FALLBACK = 'Intervals.icu cannot be reached right now. Please try again later.';
const HANDLED_ERRORS = [400, 401, 403, 404, 409, 413, 429, 502, 503];
const SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength', 'other'];
const SOURCES: readonly string[] = ['fit_file', 'tcx_file', 'gpx_file', 'manual', 'intervals_icu'];
const MANUAL_FIELDS: readonly ManualField[] = [
  'sport',
  'date',
  'time',
  'duration_minutes',
  'distance_km',
  'rpe',
  'notes',
];
const RATING_FIELDS: readonly RatingField[] = ['rpe', 'notes'];

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's activities. Problems that people can act on are values; anything
 * unexpected (network, other server errors, an answer of the wrong shape) rejects.
 */
@Injectable({ providedIn: 'root' })
export class ActivitiesApi {
  private readonly http = inject(HttpClient);

  /** One page, newest first; with `sport` only that sport. The server caps `limit` at 200. */
  async list(limit: number, offset: number, sport?: Sport): Promise<ListActivitiesResult> {
    const params: Record<string, string> = { limit: String(limit), offset: String(offset) };
    if (sport !== undefined) {
      params['sport'] = sport;
    }
    const reply = await this.send(
      this.http.get(URL, {
        params,
        observe: 'response',
      }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', page: toPage(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async get(id: string): Promise<GetActivityResult> {
    const reply = await this.send(this.http.get(urlOf(id), { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', activity: toDetail(reply) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Sends the file as it is; the server decides by its content, not by its name. */
  async import(file: File): Promise<ImportActivityResult> {
    const form = new FormData();
    form.append('file', file);
    const reply = await this.send(this.http.post(IMPORT_URL, form, { observe: 'response' }));
    switch (reply.status) {
      case 201:
        return { kind: 'imported', activity: toActivity(reply.body, reply) };
      case 400:
        return { kind: 'rejected', message: detailOf(reply.body) ?? REJECTED_FALLBACK };
      case 409:
        return { kind: 'duplicate', existingId: existingIdOf(reply) };
      case 413:
        return { kind: 'too_large' };
      case 429:
        return { kind: 'rate_limited' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Enters a session by hand; the server checks every field again and says what is wrong. */
  async enter(input: ManualActivityInput): Promise<EnterActivityResult> {
    const reply = await this.send(this.http.post(MANUAL_URL, input, { observe: 'response' }));
    switch (reply.status) {
      case 201:
        return { kind: 'entered', activity: toActivity(reply.body, reply) };
      case 400:
        return { kind: 'invalid', ...toRefusal(reply.body, MANUAL_FIELDS, REJECTED_MANUAL) };
      case 409:
        return { kind: 'duplicate', existingId: existingIdOf(reply) };
      case 429:
        return { kind: 'rate_limited' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Says how hard a session felt and adds a note; nothing else of an activity can be changed. */
  async rate(id: string, input: RatingInput): Promise<RateActivityResult> {
    const reply = await this.send(this.http.patch(urlOf(id), input, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', activity: toDetail(reply) };
      case 400:
        return { kind: 'invalid', ...toRefusal(reply.body, RATING_FIELDS, REJECTED_RATING) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async delete(id: string): Promise<DeleteActivityResult> {
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

  /** Imports recent activities from the user's connected Intervals.icu account. */
  async syncFromIntervals(): Promise<SyncActivitiesResult> {
    const reply = await this.send(this.http.post(SYNC_URL, {}, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', ...toSyncSummary(reply) };
      case 404:
        return { kind: 'not_connected' };
      case 409:
        return { kind: 'invalid_key' };
      case 429:
        return { kind: 'rate_limited' };
      case 502:
      case 503:
        return unavailable(reply);
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

/** Only the known fields are taken over, whatever else an answer might carry. */
function toPage(reply: Reply): ActivityPage {
  const body = reply.body as { count?: unknown; results?: unknown } | null;
  if (typeof body?.count !== 'number' || !Array.isArray(body.results)) {
    throw unexpected(reply);
  }
  return { count: body.count, results: body.results.map((item) => toActivity(item, reply)) };
}

function toDetail(reply: Reply): ActivityDetail {
  const laps = (reply.body as { laps?: unknown } | null)?.laps;
  if (!Array.isArray(laps)) {
    throw unexpected(reply);
  }
  return { ...toActivity(reply.body, reply), laps: laps.map((lap) => toLap(lap, reply)) };
}

function toActivity(raw: unknown, reply: Reply): Activity {
  const item = (raw ?? {}) as Record<string, unknown>;
  if (
    typeof item['id'] !== 'string' ||
    !isSource(item['source']) ||
    !isSport(item['sport']) ||
    typeof item['source_sport'] !== 'string' ||
    typeof item['start_time'] !== 'string' ||
    typeof item['manufacturer'] !== 'string' ||
    typeof item['notes'] !== 'string' ||
    typeof item['created_at'] !== 'string'
  ) {
    throw unexpected(reply);
  }
  return {
    id: item['id'],
    source: item['source'],
    sport: item['sport'],
    source_sport: item['source_sport'],
    start_time: item['start_time'],
    elapsed_seconds: numberOrNull(item['elapsed_seconds'], reply),
    timer_seconds: numberOrNull(item['timer_seconds'], reply),
    distance_m: numberOrNull(item['distance_m'], reply),
    avg_heart_rate: numberOrNull(item['avg_heart_rate'], reply),
    max_heart_rate: numberOrNull(item['max_heart_rate'], reply),
    avg_pace_s_per_km: numberOrNull(item['avg_pace_s_per_km'], reply),
    avg_power_w: numberOrNull(item['avg_power_w'], reply),
    total_ascent_m: numberOrNull(item['total_ascent_m'], reply),
    calories: numberOrNull(item['calories'], reply),
    training_load: numberOrNull(item['training_load'], reply),
    manufacturer: item['manufacturer'],
    rpe: numberOrNull(item['rpe'], reply),
    notes: item['notes'],
    load: numberOrNull(item['load'], reply),
    created_at: item['created_at'],
  };
}

function toLap(raw: unknown, reply: Reply): Lap {
  const lap = (raw ?? {}) as Record<string, unknown>;
  const start = lap['start_time'] ?? null;
  if (start !== null && typeof start !== 'string') {
    throw unexpected(reply);
  }
  return {
    start_time: start,
    elapsed_seconds: numberOrNull(lap['elapsed_seconds'], reply),
    distance_m: numberOrNull(lap['distance_m'], reply),
    avg_heart_rate: numberOrNull(lap['avg_heart_rate'], reply),
    max_heart_rate: numberOrNull(lap['max_heart_rate'], reply),
  };
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

function isSport(value: unknown): value is Sport {
  return typeof value === 'string' && SPORTS.includes(value);
}

function isSource(value: unknown): value is ActivitySource {
  return typeof value === 'string' && SOURCES.includes(value);
}

function existingIdOf(reply: Reply): string {
  const existingId = (reply.body as { existing_id?: unknown } | null)?.existing_id;
  if (typeof existingId !== 'string' || !existingId) {
    throw unexpected(reply);
  }
  return existingId;
}

/**
 * The messages of a refusal by field. Only the fields of the form are taken over, and only text
 * messages; an answer without any of them (the JSON could not be read at all) gives its `detail`.
 */
function toRefusal<F extends string>(
  body: unknown,
  fields: readonly F[],
  fallback: string,
): { errors: Partial<Record<F, string[]>>; message: string | null } {
  const errors: Partial<Record<F, string[]>> = {};
  const item = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  for (const field of fields) {
    const messages = item[field];
    if (Array.isArray(messages)) {
      const texts = messages.filter((m): m is string => typeof m === 'string' && m !== '');
      if (texts.length > 0) {
        errors[field] = texts;
      }
    }
  }
  return {
    errors,
    message: Object.keys(errors).length > 0 ? null : (detailOf(body) ?? fallback),
  };
}

function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' && detail ? detail : null;
}

function toSyncSummary(reply: Reply): {
  imported: number;
  skipped_duplicates: number;
  skipped_strava: number;
  skipped_invalid: number;
  last_sync_at: string | null;
} {
  if (typeof reply.body !== 'object' || reply.body === null || Array.isArray(reply.body)) {
    throw unexpected(reply);
  }
  const item = reply.body as Record<string, unknown>;
  const lastSyncAt = item['last_sync_at'];
  if (lastSyncAt !== null && typeof lastSyncAt !== 'string') {
    throw unexpected(reply);
  }
  return {
    imported: nonNegativeInt(item['imported'], reply),
    skipped_duplicates: nonNegativeInt(item['skipped_duplicates'], reply),
    skipped_strava: nonNegativeInt(item['skipped_strava'], reply),
    skipped_invalid: nonNegativeInt(item['skipped_invalid'], reply),
    last_sync_at: lastSyncAt,
  };
}

function nonNegativeInt(value: unknown, reply: Reply): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw unexpected(reply);
  }
  return value;
}

function unavailable(reply: Reply): Unavailable {
  return {
    kind: 'unavailable',
    message: detailOf(reply.body) ?? UNAVAILABLE_FALLBACK,
  };
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
