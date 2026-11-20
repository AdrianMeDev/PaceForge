/** The signed-in user as returned by `GET /api/me/`. */
export interface Me {
  id: string;
  email: string;
  display_name: string;
  is_staff: boolean;
  /** An authenticator app (TOTP) is active. */
  mfa_enabled: boolean;
  /** An administrator who has not turned on two-factor authentication yet. */
  mfa_setup_required: boolean;
}

/** A step of an authentication flow, e.g. `login`, `verify_email` or `mfa_authenticate`. */
export interface AuthFlow {
  id: string;
  is_pending?: boolean;
  /** For `mfa_authenticate`: the kinds of second factor the account has. */
  types?: string[];
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

/** The second step of a sign-in with two-factor authentication. */
export type MfaAuthenticateResult =
  | { kind: 'authenticated' }
  | { kind: 'invalid'; errors: ApiError[] }
  /** There is no half-finished sign-in any more (the session ran out). */
  | { kind: 'expired' };

export type ReauthenticateResult =
  { kind: 'confirmed' } | { kind: 'invalid'; errors: ApiError[] } | { kind: 'rate_limited' };

/**
 * Turning two-factor authentication on or off and handling recovery codes need the password
 * again, even right after signing in. The server says so with 401 and a `reauthenticate` flow;
 * the caller asks for the password, calls `reauthenticate` and repeats the action.
 */
export interface ReauthenticationRequired {
  kind: 'reauthentication_required';
}

/** `inactive` carries what the setup needs: the secret and the URL for the QR code. */
export type TotpStatus =
  | { kind: 'active'; createdAt: number; lastUsedAt: number | null }
  | { kind: 'inactive'; secret: string; totpUrl: string };

export type ActivateTotpResult =
  { kind: 'activated' } | { kind: 'invalid'; errors: ApiError[] } | ReauthenticationRequired;

export type DeactivateTotpResult = { kind: 'deactivated' } | ReauthenticationRequired;

export interface RecoveryCodeSet {
  /** The codes that can still be used. */
  codes: string[];
  total: number;
  unused: number;
}

export type RecoveryCodesResult =
  ({ kind: 'codes' } & RecoveryCodeSet) | { kind: 'none' } | ReauthenticationRequired;

export type RegenerateRecoveryCodesResult =
  ({ kind: 'regenerated' } & RecoveryCodeSet) | ReauthenticationRequired;

/** `file` is the JSON export; `filename` is the name the server suggests for it. */
export type AccountExportResult =
  | { kind: 'exported'; file: Blob; filename: string }
  | { kind: 'forbidden' }
  | { kind: 'rate_limited' };

/** What the athlete typed to delete the account. Nothing here is kept after the request. */
export interface DeleteAccountRequest {
  /** The email address of the account, typed again. */
  confirmation: string;
  password: string;
  /** Authenticator or recovery code; needed only when two-factor authentication is on. */
  mfaCode?: string;
}

/** `invalid` carries one error per field (`confirmation`, `password`, `mfa_code`). */
export type DeleteAccountResult =
  | { kind: 'deleted' }
  | { kind: 'invalid'; errors: ApiError[] }
  | { kind: 'forbidden' }
  | { kind: 'last_admin' }
  | { kind: 'rate_limited' };
