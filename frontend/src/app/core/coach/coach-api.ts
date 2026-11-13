import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  AiProviderInput,
  AiProviderKind,
  AiProviderState,
  AiStatus,
  AiUsage,
  CheckOutcome,
  CheckProblem,
  CheckProviderResult,
  GetProviderResult,
  Invalid,
  RemoveProviderResult,
  SaveProviderResult,
} from './coach-models';

const URL = `${API_BASE}/coach/provider/`;
const CHECK_URL = `${URL}check/`;
const INVALID_FALLBACK = 'The input was not accepted.';
const HANDLED_ERRORS = [400, 401, 403, 404, 429];
const PROVIDERS: readonly string[] = ['anthropic', 'openai_compatible'];
const STATUSES: readonly string[] = ['untested', 'connected', 'invalid', 'unavailable'];
const PROBLEMS: readonly string[] = [
  'invalid_key',
  'rate_limited',
  'unavailable',
  'unexpected',
  'not_allowed',
];

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's AI provider. Problems that people can act on are values; anything
 * unexpected (network, other server errors, an answer of the wrong shape) rejects. The key is
 * sent in `save()` and nowhere else, and no result carries it: nothing is taken over from an
 * answer but the known fields.
 */
@Injectable({ providedIn: 'root' })
export class CoachApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetProviderResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', state: toState(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Sets the provider up or changes it; the answer is the whole setup as it is now. */
  async save(input: AiProviderInput): Promise<SaveProviderResult> {
    const reply = await this.send(this.http.put(URL, input, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', state: toState(reply.body, reply) };
      case 400:
        return invalid(reply);
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Removing a setup that does not exist is fine. The key goes with it. */
  async remove(): Promise<RemoveProviderResult> {
    const reply = await this.send(this.http.delete(URL, { observe: 'response' }));
    switch (reply.status) {
      case 204:
        return { kind: 'removed' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /**
   * Sends a tiny fixed prompt with the user's own key. That the provider refuses the key is a
   * result of the check, not a failure of the call: `check.ok` says how it went.
   */
  async check(): Promise<CheckProviderResult> {
    const reply = await this.send(this.http.post(CHECK_URL, {}, { observe: 'response' }));
    switch (reply.status) {
      case 200: {
        const body = asObject(reply.body, reply);
        return {
          kind: 'checked',
          state: toState(body, reply),
          check: toCheck(body['check'], reply),
        };
      }
      case 404:
        return { kind: 'not_configured' };
      case 429:
        return { kind: 'rate_limited' };
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

/** Only the known fields are taken over, whatever else an answer might carry (never a key). */
function toState(raw: unknown, reply: Reply): AiProviderState {
  const item = asObject(raw, reply);
  const provider = item['provider'];
  const status = item['status'];
  const baseUrl = item['base_url'];
  const allowed = item['allowed_base_urls'];
  if (
    typeof item['configured'] !== 'boolean' ||
    (provider !== null && !isOneOf<AiProviderKind>(provider, PROVIDERS)) ||
    typeof item['model'] !== 'string' ||
    (baseUrl !== null && typeof baseUrl !== 'string') ||
    typeof item['has_key'] !== 'boolean' ||
    (status !== null && !isOneOf<AiStatus>(status, STATUSES)) ||
    !isTimestampOrNull(item['last_checked_at']) ||
    !isTimestampOrNull(item['last_success_at']) ||
    !Array.isArray(allowed) ||
    !allowed.every((address) => typeof address === 'string') ||
    // A setup has a provider and a status; no setup has neither.
    item['configured'] !== (provider !== null) ||
    item['configured'] !== (status !== null)
  ) {
    throw unexpected(reply);
  }
  return {
    configured: item['configured'],
    provider,
    model: item['model'],
    base_url: baseUrl,
    has_key: item['has_key'],
    status,
    last_checked_at: item['last_checked_at'],
    last_success_at: item['last_success_at'],
    allowed_base_urls: [...(allowed as string[])],
    usage: toUsage(item['usage'], reply),
  };
}

function toUsage(raw: unknown, reply: Reply): AiUsage {
  const item = asObject(raw, reply);
  const { calls, input_tokens, output_tokens, days } = item;
  if (
    !isCount(calls) ||
    !isCount(input_tokens) ||
    !isCount(output_tokens) ||
    !isCount(days) ||
    days < 1
  ) {
    throw unexpected(reply);
  }
  return { calls, input_tokens, output_tokens, days };
}

function toCheck(raw: unknown, reply: Reply): CheckOutcome {
  const item = asObject(raw, reply);
  const { ok, problem, message } = item;
  const retryAfter = item['retry_after'];
  if (
    typeof ok !== 'boolean' ||
    (problem !== null && !isOneOf<CheckProblem>(problem, PROBLEMS)) ||
    typeof message !== 'string' ||
    (retryAfter !== null && !isCount(retryAfter)) ||
    // A check went well exactly when there is no problem.
    ok !== (problem === null)
  ) {
    throw unexpected(reply);
  }
  return { ok, problem, message, retry_after: retryAfter };
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

function isTimestampOrNull(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && !Number.isNaN(Date.parse(value)));
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

/**
 * DRF reports field errors as `{"api_key": ["…"]}` and other problems as `{"detail": "…"}` or
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
