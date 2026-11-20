import { Invalid } from '../goals/goals-models';
import { UnexpectedReplyError } from './failures';
import {
  Finding,
  GenerateResult,
  PlanProblem,
  ProviderProblem,
  Report,
  Severity,
} from '../planning/planning-models';

const INVALID_FALLBACK = 'The input was not accepted.';
const FALLBACK_TEXT = 'The AI provider could not be used right now. Please try again later.';
const SEVERITIES: readonly string[] = ['error', 'warning'];
const PROBLEMS: readonly string[] = [
  'invalid_key',
  'rate_limited',
  'unavailable',
  'too_slow',
  'unexpected',
  'not_allowed',
];
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * The parsing that the week plan and the season plan share: the answers about the coach (a report
 * of checks, the problems of an answer that could not be used, a rate limit, a problem of the
 * provider) and the checks of single fields. Everything unexpected rejects.
 */

/** What the server answered, as the `send` of an API hands it to the parsing. */
export interface Reply {
  status: number;
  body: unknown;
}

/** The provider refused or could not be reached (the server's text for users comes with it). */
export type ProviderProblemResult = Extract<GenerateResult, { kind: 'provider_problem' }>;

export function toReport(raw: unknown, reply: Reply): Report {
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

export function toFindings(item: Record<string, unknown>, reply: Reply): Finding[] {
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
export function codeOf(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return null;
  }
  const code = (body as Record<string, unknown>)['code'];
  return typeof code === 'string' ? code : null;
}

export function toProblems(reply: Reply): PlanProblem[] {
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
export function toRateLimit(reply: Reply): ProviderProblemResult | { kind: 'rate_limited' } {
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
export function toProviderProblem(reply: Reply, fallback: ProviderProblem): ProviderProblemResult {
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

export function asObject(raw: unknown, reply: Reply): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw unexpected(reply);
  }
  return raw as Record<string, unknown>;
}

export function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

export function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

export function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

export function unexpected(reply: Reply): Error {
  return new UnexpectedReplyError(reply.status);
}

/**
 * DRF reports field errors as `{"api_key": ["…"]}` and other problems as `{"detail": "…"}` or
 * `{"non_field_errors": ["…"]}`. All messages are kept, by field and as one list.
 */
export function toInvalid(reply: Reply): Invalid {
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
