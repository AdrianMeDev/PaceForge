export type InvitationStatus = 'pending' | 'used' | 'revoked' | 'expired';

/** One invitation as the admin API lists it. The link is never part of it. */
export interface Invitation {
  id: string;
  email: string;
  status: InvitationStatus;
  /** ISO 8601 timestamps. */
  created_at: string;
  expires_at: string;
  /** When the invitation mail last went out; `null` while it never did. */
  sent_at: string | null;
}

/**
 * Why the admin API refused. `mfa_required`: an administrator who has not turned on two-factor
 * authentication yet (the SPA sends them to the security page); `forbidden`: anything else.
 */
export type Denied = { kind: 'mfa_required' } | { kind: 'forbidden' };

export type ListInvitationsResult = { kind: 'ok'; invitations: Invitation[] } | Denied;

/**
 * `inviteUrl` exists only in the answer to the creating request: the server keeps just a hash.
 * `emailSent` is `false` when the mail could not be delivered; the link still works.
 */
export type CreateInvitationResult =
  | { kind: 'created'; invitation: Invitation; inviteUrl: string; emailSent: boolean }
  | { kind: 'invalid'; errors: string[] }
  | { kind: 'rate_limited' }
  | Denied;

/** Like creating, resending issues a new link, so it is returned here as well. */
export type ResendInvitationResult =
  | { kind: 'resent'; invitation: Invitation; inviteUrl: string; emailSent: boolean }
  /** The invitation was already used or revoked and cannot be sent again. */
  | { kind: 'conflict' }
  | { kind: 'not_found' }
  | { kind: 'rate_limited' }
  | Denied;

export type RevokeInvitationResult =
  | { kind: 'revoked'; invitation: Invitation }
  /** The invitation was already used and cannot be revoked any more. */
  | { kind: 'conflict' }
  | { kind: 'not_found' }
  | Denied;
