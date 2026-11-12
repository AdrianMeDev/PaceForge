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

/** Everything needed to create an account from an invitation link. */
export interface SignupRequest {
  email: string;
  password: string;
  invitationToken: string;
}

/**
 * Result of a signup. `pending` is the normal success: the account exists but the email address
 * still has to be verified. `authenticated` only happens if verification is switched off.
 */
export type SignupResult =
  | { kind: 'pending'; flows: AuthFlow[] }
  | { kind: 'authenticated' }
  | { kind: 'invalid'; errors: ApiError[] }
  | { kind: 'closed' }
  | { kind: 'rate_limited' };

/** What the verification link in an email is about, fetched without confirming anything. */
export type EmailVerificationInfo =
  { kind: 'valid'; email: string } | { kind: 'invalid'; errors: ApiError[] };

/** `authenticated`: the confirmation also signed the user in; `verified`: sign in as usual. */
export type VerifyEmailResult =
  { kind: 'authenticated' } | { kind: 'verified' } | { kind: 'invalid'; errors: ApiError[] };

/** The server always answers `sent`, whether or not the address belongs to an account. */
export type PasswordResetRequestResult =
  { kind: 'sent' } | { kind: 'invalid'; errors: ApiError[] } | { kind: 'rate_limited' };

export type PasswordResetKeyResult =
  { kind: 'valid' } | { kind: 'invalid'; errors: ApiError[] } | { kind: 'rate_limited' };

/** A finished reset does not sign the user in. */
export type PasswordResetResult =
  { kind: 'done' } | { kind: 'invalid'; errors: ApiError[] } | { kind: 'rate_limited' };
