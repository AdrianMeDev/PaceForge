import { Forbidden, Invalid } from '../goals/goals-models';
import { RateLimited } from '../integrations/intervals-models';

export type { Forbidden, Invalid, RateLimited };

export type AiProviderKind = 'anthropic' | 'openai_compatible';
/**
 * `untested`: nothing has been tried since the setup changed; `invalid`: the provider refused the
 * key; `unavailable`: the provider could not be reached at the last try.
 */
export type AiStatus = 'untested' | 'connected' | 'invalid' | 'unavailable';
/** What went wrong in a connection check (the server's fixed texts come with it). */
export type CheckProblem =
  'invalid_key' | 'rate_limited' | 'unavailable' | 'unexpected' | 'not_allowed';

/** What the user has used of their own provider in the last `days` days, failed calls included. */
export interface AiUsage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  days: number;
}

/**
 * The user's AI provider setup. The key is not part of it and never comes back from the server:
 * `has_key` only says that one is stored. `allowed_base_urls` are the addresses the operator
 * allows for OpenAI-compatible endpoints (empty: none, so only Anthropic can be chosen).
 * Timestamps are ISO 8601.
 */
export interface AiProviderState {
  configured: boolean;
  provider: AiProviderKind | null;
  model: string;
  base_url: string | null;
  has_key: boolean;
  status: AiStatus | null;
  last_checked_at: string | null;
  last_success_at: string | null;
  allowed_base_urls: string[];
  usage: AiUsage;
}

/**
 * What is sent to set the provider up. `api_key` left out keeps the stored key (only while
 * provider and address stay the same); an empty text means no key (only OpenAI-compatible
 * endpoints can do without). `base_url` is for OpenAI-compatible endpoints only.
 */
export interface AiProviderInput {
  provider: AiProviderKind;
  model: string;
  base_url?: string;
  api_key?: string;
}

/** The result of a connection check. `message` is the server's text for users, empty if `ok`. */
export interface CheckOutcome {
  ok: boolean;
  problem: CheckProblem | null;
  message: string;
  /** Seconds the provider asked to wait, if it said. */
  retry_after: number | null;
}

export type GetProviderResult = { kind: 'ok'; state: AiProviderState } | Forbidden;
export type SaveProviderResult = { kind: 'ok'; state: AiProviderState } | Invalid | Forbidden;
export type RemoveProviderResult = { kind: 'removed' } | Forbidden;
export type CheckProviderResult =
  /** The check ran; `state` is the setup afterwards (its status may have changed). */
  | { kind: 'checked'; state: AiProviderState; check: CheckOutcome }
  | { kind: 'not_configured' }
  | RateLimited
  | Forbidden;
