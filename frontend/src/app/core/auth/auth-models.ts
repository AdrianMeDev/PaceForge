/** The signed-in user as returned by `GET /api/me/`. */
export interface Me {
  id: string;
  email: string;
  display_name: string;
  is_staff: boolean;
}

/** A step of an authentication flow, e.g. `login`, `verify_email` or `mfa_authenticate`. */
export interface AuthFlow {
  id: string;
  is_pending?: boolean;
}

/** One validation or domain error from the allauth headless API. */
export interface ApiError {
  code: string;
  message: string;
  param?: string;
}

/** Result of asking the server who the current visitor is. */
export type SessionResult = { kind: 'authenticated' } | { kind: 'anonymous'; flows: AuthFlow[] };

/** Result of a login attempt; failures that users can fix are values, not exceptions. */
export type LoginResult =
  | { kind: 'authenticated' }
  | { kind: 'pending'; flows: AuthFlow[] }
  | { kind: 'invalid'; errors: ApiError[] };

/** Same as {@link LoginResult} but after the user data has been loaded. */
export type LoginOutcome = Exclude<LoginResult, { kind: 'authenticated' }> | { kind: 'success' };

/** `unavailable` means the server could not be reached or answered unexpectedly. */
export type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'unavailable';
