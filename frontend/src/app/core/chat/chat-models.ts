import { Forbidden } from '../goals/goals-models';
import { RateLimited } from '../integrations/intervals-models';
import { ProviderProblem } from '../planning/planning-models';

export type { Forbidden, RateLimited };

export type ChatRole = 'user' | 'coach';

/** The draft of a week that the coach made from a message. */
export interface ChatPlan {
  id: string;
  /** The Monday, YYYY-MM-DD. */
  week_start: string;
}

/**
 * One message of the conversation. `text` is the athlete's own or the coach's and is shown as text
 * only. `changes` are sentences the server made from what it changed (never the coach's words);
 * `plan` is the draft they went into, `null` for a message that changed nothing.
 */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  created_at: string;
  changes: string[];
  plan: ChatPlan | null;
}

export type ListMessagesResult = { kind: 'ok'; messages: ChatMessage[] } | Forbidden;

export type SendMessageResult =
  /** The message of the athlete and the answer of the coach, as they were stored. */
  | { kind: 'ok'; messages: ChatMessage[] }
  /** The message cannot be used (empty, too long …); `errors` are texts for the user. */
  | { kind: 'invalid'; errors: string[] }
  /** No AI provider is set up. */
  | { kind: 'not_configured' }
  /** The provider refused or could not be reached; `message` is the server's text for users. */
  | {
      kind: 'provider_problem';
      problem: ProviderProblem;
      message: string;
      retry_after: number | null;
    }
  /** Too many messages in a short time (this server's limit, not the provider's). */
  | RateLimited
  | Forbidden;

export type ClearMessagesResult = { kind: 'cleared' } | Forbidden;
