/** Read either a fragment invitation or a legacy query invitation, decoding once. */
export function readInvitationLink(url: string): { invitationToken: string; email: string } {
  const link = new URL(url);
  const fragment = new URLSearchParams(link.hash.slice(1));
  const params = fragment.has('invitation') ? fragment : link.searchParams;
  return {
    invitationToken: (params.get('invitation') ?? '').trim(),
    email: (params.get('email') ?? '').trim(),
  };
}
