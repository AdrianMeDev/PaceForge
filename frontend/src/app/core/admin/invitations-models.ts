export type InvitationStatus = 'pending' | 'used' | 'revoked' | 'expired';

/** One invitation as the admin API lists it. The link is never part of it. */
export interface Invitation {
  id: string;
  email: string;
  status: InvitationStatus;
  /** ISO 8601 timestamps. */
  created_at: string;
  expires_at: string;
}

/**
 * Why the admin API refused. `mfa_required`: an administrator who has not turned on two-factor
 * authentication yet (the SPA sends them to the security page); `forbidden`: anything else.
 */
export type Denied = { kind: 'mfa_required' } | { kind: 'forbidden' };

export type ListInvitationsResult = { kind: 'ok'; invitations: Invitation[] } | Denied;

/** `inviteUrl` exists only in the answer to the creating request: the server keeps just a hash. */
export type CreateInvitationResult =
  | { kind: 'created'; invitation: Invitation; inviteUrl: string }
  | { kind: 'invalid'; errors: string[] }
  | Denied;

export type RevokeInvitationResult =
  | { kind: 'revoked'; invitation: Invitation }
  /** The invitation was already used and cannot be revoked any more. */
  | { kind: 'conflict' }
  | { kind: 'not_found' }
  | Denied;
