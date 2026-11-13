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
  GetActivityResult,
  ImportActivityResult,
  Lap,
  ListActivitiesResult,
  Sport,
} from './activities-models';

const URL = `${API_BASE}/activities/`;
const IMPORT_URL = `${URL}import/`;
const REJECTED_FALLBACK = 'The file could not be imported.';
const HANDLED_ERRORS = [400, 401, 403, 404, 409, 413, 429];
const SPORTS: readonly string[] = ['running', 'cycling', 'swimming', 'strength', 'other'];
const SOURCES: readonly string[] = ['fit_file', 'tcx_file'];

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

  /** One page, newest first. The server caps `limit` at 200. */
  async list(limit: number, offset: number): Promise<ListActivitiesResult> {
    const reply = await this.send(
      this.http.get(URL, {
        params: { limit: String(limit), offset: String(offset) },
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
      case 409: {
        const existingId = (reply.body as { existing_id?: unknown } | null)?.existing_id;
        if (typeof existingId !== 'string' || !existingId) {
          throw unexpected(reply);
        }
        return { kind: 'duplicate', existingId };
      }
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
    avg_power_w: numberOrNull(item['avg_power_w'], reply),
    total_ascent_m: numberOrNull(item['total_ascent_m'], reply),
    calories: numberOrNull(item['calories'], reply),
    manufacturer: item['manufacturer'],
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

function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' && detail ? detail : null;
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
