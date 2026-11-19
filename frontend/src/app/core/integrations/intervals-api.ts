import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  CheckConnectionResult,
  ConnectResult,
  ConnectionStatus,
  DisconnectResult,
  GetConnectionResult,
  IntervalsConnection,
  SyncErrorCode,
  Unavailable,
} from './intervals-models';

const URL = `${API_BASE}/integrations/intervals/`;
const CHECK_URL = `${URL}check/`;
const INVALID_FALLBACK = 'The key was not accepted.';
const UNAVAILABLE_FALLBACK = 'Intervals.icu cannot be reached right now. Please try again later.';
const HANDLED_ERRORS = [400, 401, 403, 404, 429, 502, 503];

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's Intervals.icu connection. Problems that people can act on are values;
 * anything unexpected (network, other server errors, an answer of the wrong shape) rejects.
 * The key is sent in `connect()` and nowhere else, and no result carries it.
 */
@Injectable({ providedIn: 'root' })
export class IntervalsConnectionApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetConnectionResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return (reply.body as { connected?: unknown } | null)?.connected === false
          ? { kind: 'not_connected' }
          : { kind: 'connected', connection: toConnection(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async connect(apiKey: string): Promise<ConnectResult> {
    const reply = await this.send(this.http.put(URL, { api_key: apiKey }, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'connected', connection: toConnection(reply) };
      case 400:
        return { kind: 'invalid_key', errors: messagesOf(reply.body) };
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

  async check(): Promise<CheckConnectionResult> {
    const reply = await this.send(this.http.post(CHECK_URL, {}, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'checked', connection: toConnection(reply) };
      case 404:
        return { kind: 'not_connected' };
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

  /** Removing a connection that does not exist is fine. */
  async disconnect(): Promise<DisconnectResult> {
    const reply = await this.send(this.http.delete(URL, { observe: 'response' }));
    switch (reply.status) {
      case 204:
        return { kind: 'disconnected' };
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

const SYNC_ERRORS: readonly SyncErrorCode[] = ['', 'invalid_key', 'unavailable', 'unexpected'];

/** Only the known fields are taken over, whatever else an answer might carry. */
function toConnection(reply: Reply): IntervalsConnection {
  const body = reply.body as Record<string, unknown> | null;
  const { status, athlete_id, connected_at, last_checked_at, last_sync_at, last_sync_error } =
    body ?? {};
  if (
    !isStatus(status) ||
    typeof athlete_id !== 'string' ||
    typeof connected_at !== 'string' ||
    typeof last_checked_at !== 'string' ||
    (last_sync_at !== null && typeof last_sync_at !== 'string') ||
    !isSyncErrorCode(last_sync_error)
  ) {
    throw unexpected(reply);
  }
  return { status, athlete_id, connected_at, last_checked_at, last_sync_at, last_sync_error };
}

function isStatus(value: unknown): value is ConnectionStatus {
  return value === 'connected' || value === 'invalid';
}

function isSyncErrorCode(value: unknown): value is SyncErrorCode {
  return typeof value === 'string' && SYNC_ERRORS.includes(value as SyncErrorCode);
}

/** DRF reports field errors as `{"api_key": ["…"]}`; all messages are collected. */
function messagesOf(body: unknown): string[] {
  if (typeof body !== 'object' || body === null) {
    return [INVALID_FALLBACK];
  }
  const messages = Object.values(body)
    .flat()
    .filter((value): value is string => typeof value === 'string');
  return messages.length ? messages : [INVALID_FALLBACK];
}

function unavailable(reply: Reply): Unavailable {
  const detail = (reply.body as { detail?: unknown } | null)?.detail;
  return {
    kind: 'unavailable',
    message: typeof detail === 'string' && detail ? detail : UNAVAILABLE_FALLBACK,
  };
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
