export type ConnectionStatus = 'connected' | 'invalid';

export type SyncErrorCode = '' | 'invalid_key' | 'unavailable' | 'unexpected';

/**
 * The state of the signed-in user's Intervals.icu connection. The API key is not part of it and
 * never comes back from the server; it only travels in the request that saves it.
 */
export interface IntervalsConnection {
  /** `invalid`: Intervals.icu refused the stored key at the last check. */
  status: ConnectionStatus;
  /** The account at Intervals.icu, e.g. `i123456`. */
  athlete_id: string;
  /** ISO 8601 timestamps. */
  connected_at: string;
  last_checked_at: string;
  last_sync_at: string | null;
  /** Fixed error code from the last sync attempt, or `''` when none. */
  last_sync_error: SyncErrorCode;
}

/** The session is gone or the request was refused (CSRF): the user has to sign in again. */
export interface Forbidden {
  kind: 'forbidden';
}

/** Too many tries; the server asks to wait. */
export interface RateLimited {
  kind: 'rate_limited';
}

/** Intervals.icu cannot be reached or answered oddly. `message` is the server's text for users. */
export interface Unavailable {
  kind: 'unavailable';
  message: string;
}

export type GetConnectionResult =
  { kind: 'not_connected' } | { kind: 'connected'; connection: IntervalsConnection } | Forbidden;

export type ConnectResult =
  | { kind: 'connected'; connection: IntervalsConnection }
  /** The key was not accepted (or was empty); `errors` are messages for the user. */
  | { kind: 'invalid_key'; errors: string[] }
  | RateLimited
  | Unavailable
  | Forbidden;

export type CheckConnectionResult =
  /** The connection with the result of the check; its status may now be `invalid`. */
  | { kind: 'checked'; connection: IntervalsConnection }
  | { kind: 'not_connected' }
  | RateLimited
  | Unavailable
  | Forbidden;

export type DisconnectResult = { kind: 'disconnected' } | Forbidden;
