import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import { UnexpectedReplyError } from '../api/failures';
import { ProviderProblem } from '../planning/planning-models';
import {
  ChatMessage,
  ChatRole,
  ClearMessagesResult,
  ListMessagesResult,
  SendMessageResult,
} from './chat-models';

const URL = `${API_BASE}/chat/messages/`;
const HANDLED_ERRORS = [400, 401, 403, 409, 429, 502, 503];
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ROLES: readonly string[] = ['user', 'coach'];
const INVALID_FALLBACK = 'Your message could not be sent. Please check it.';
const PROVIDER_FALLBACK = 'The AI provider could not be used right now. Please try again later.';
const PROVIDER_PROBLEMS: readonly string[] = [
  'invalid_key',
  'rate_limited',
  'unavailable',
  'too_slow',
  'unexpected',
  'not_allowed',
];

interface Reply {
  status: number;
  body: unknown;
}

type Raw = Record<string, unknown>;

/**
 * The conversation of the signed-in user with their coach. Problems that people can act on are
 * values; anything unexpected (network, other server errors, an answer of the wrong shape)
 * rejects. Every field of a message is checked, so that what arrives here can be shown as it is.
 */
@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  /** The whole conversation, the oldest message first. */
  async list(): Promise<ListMessagesResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', messages: toMessages(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Writes to the coach. The coach may take a minute or two to answer, so this waits; the answer
   * is the athlete's message and the coach's, as they were stored.
   */
  async write(text: string): Promise<SendMessageResult> {
    const reply = await this.send(this.http.post(URL, { text }, { observe: 'response' }));
    switch (reply.status) {
      case 201:
        return { kind: 'ok', messages: toMessages(reply) };
      case 400:
        return { kind: 'invalid', errors: toErrors(reply) };
      case 409:
        if (codeOf(reply.body) === 'not_configured') {
          return { kind: 'not_configured' };
        }
        throw unexpected(reply);
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

  /** Deletes the whole conversation (the drafts that came of it stay). */
  async clear(): Promise<ClearMessagesResult> {
    const reply = await this.send(this.http.delete(URL, { observe: 'response' }));
    switch (reply.status) {
      case 204:
        return { kind: 'cleared' };
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

function toMessages(reply: Reply): ChatMessage[] {
  return list(object(reply.body, reply)['messages'], reply).map((raw) => toMessage(raw, reply));
}

function toMessage(raw: unknown, reply: Reply): ChatMessage {
  const item = object(raw, reply);
  const plan = item['plan'];
  const seasonPlan = item['season_plan'];
  return {
    id: text(item['id'], reply),
    role: oneOf(item['role'], ROLES, reply) as ChatRole,
    text: text(item['text'], reply),
    created_at: text(item['created_at'], reply),
    changes: list(item['changes'], reply).map((entry) => text(entry, reply)),
    plan:
      plan === null
        ? null
        : { id: text(object(plan, reply)['id'], reply), week_start: weekOf(plan, reply) },
    season_plan:
      seasonPlan === null
        ? null
        : {
            id: text(object(seasonPlan, reply)['id'], reply),
            version: versionOf(seasonPlan, reply),
          },
  };
}

function weekOf(plan: unknown, reply: Reply): string {
  const found = string(object(plan, reply)['week_start'], reply);
  if (!DATE.test(found)) {
    throw unexpected(reply);
  }
  return found;
}

/** The number of a version of the season plan: a whole number, counted from 1. */
function versionOf(plan: unknown, reply: Reply): number {
  const found = object(plan, reply)['version'];
  if (typeof found !== 'number' || !Number.isInteger(found) || found < 1) {
    throw unexpected(reply);
  }
  return found;
}

function toErrors(reply: Reply): string[] {
  const body = reply.body;
  if (typeof body === 'object' && body !== null && Array.isArray((body as Raw)['errors'])) {
    const errors = ((body as Raw)['errors'] as unknown[]).filter(
      (entry): entry is string => typeof entry === 'string' && entry !== '',
    );
    if (errors.length > 0) {
      return errors;
    }
  }
  return [INVALID_FALLBACK];
}

/**
 * 429 comes from two places: the provider asking to slow down (the body has a code and the
 * server's text) and this server's own limit (a plain throttling answer without a code).
 */
function toRateLimit(reply: Reply): SendMessageResult {
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
function toProviderProblem(reply: Reply, fallback: ProviderProblem): SendMessageResult {
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

/** Text that must not be empty: an id, a timestamp or a message. */
function text(value: unknown, reply: Reply): string {
  const found = string(value, reply);
  if (found === '') {
    throw unexpected(reply);
  }
  return found;
}

function oneOf(value: unknown, allowed: readonly string[], reply: Reply): string {
  if (typeof value !== 'string' || !allowed.includes(value)) {
    throw unexpected(reply);
  }
  return value;
}

function unexpected(reply: Reply): Error {
  return new UnexpectedReplyError(reply.status);
}
