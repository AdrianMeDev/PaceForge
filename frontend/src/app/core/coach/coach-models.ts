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
  /** All input tokens, the cached ones included. */
  input_tokens: number;
  output_tokens: number;
  /** The parts of `input_tokens` that were read from the provider's prompt cache and written to it. */
  cache_read_tokens: number;
  cache_write_tokens: number;
  days: number;
}

/**
 * How long an Anthropic model may think before it answers. Not every model takes every level.
 */
export type AiEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

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
  /** The model for the season plan; empty: the normal model does it. */
  season_model: string;
  /** The model for the week plan; empty: the normal model does it. */
  week_model: string;
  /** The model for the coach chat; empty: the normal model does it. */
  chat_model: string;
  /** Anthropic only. Empty: none is sent and the model uses its own default. */
  effort: AiEffort | '';
  /** The effort for the season plan, the week plan and the chat; empty: the normal effort. */
  season_effort: AiEffort | '';
  week_effort: AiEffort | '';
  chat_effort: AiEffort | '';
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
  /** Empty: the season plan uses the normal model. */
  season_model?: string;
  /** Empty: the week plan uses the normal model. */
  week_model?: string;
  /** Empty: the coach chat uses the normal model. */
  chat_model?: string;
  /** Anthropic only; left out or empty: none (for the tasks: the normal effort). */
  effort?: AiEffort | '';
  season_effort?: AiEffort | '';
  week_effort?: AiEffort | '';
  chat_effort?: AiEffort | '';
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

/**
 * What one million tokens of a model cost. Prices are decimal texts as the server writes them
 * (for example `"3.0000"`); `cached_per_million` is `null` if no price is set for cached input.
 */
export interface ModelPrice {
  id: number;
  model: string;
  input_per_million: string;
  output_per_million: string;
  cached_per_million: string | null;
}

/** What is sent to set the price of one model; a cached price left out or `null` means none. */
export interface ModelPriceInput {
  model: string;
  input_per_million: number;
  output_per_million: number;
  cached_per_million?: number | null;
}

/** The calls of one calendar month (`month` is `YYYY-MM`, in the user's time zone). */
export interface MonthlyUsage {
  month: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  /** Decimal text; `null` if no model used in the month has a price. */
  cost: string | null;
  /** The models used in the month that have no price; their calls are not in `cost`. */
  unpriced_models: string[];
}

/** The user's prices and their monthly usage, newest month first. */
export interface AiCostsState {
  prices: ModelPrice[];
  months: MonthlyUsage[];
}

export interface PriceNotFound {
  kind: 'not_found';
}

export type GetCostsResult = { kind: 'ok'; state: AiCostsState } | Forbidden;
export type SavePriceResult = { kind: 'ok'; state: AiCostsState } | Invalid | Forbidden;
export type DeletePriceResult = { kind: 'deleted' } | PriceNotFound | Forbidden;
