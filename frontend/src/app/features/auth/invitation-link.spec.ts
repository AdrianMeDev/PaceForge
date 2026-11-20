import { readInvitationLink } from './invitation-link';

const SIGNUP = 'https://paceforge.example/account/signup';

describe('readInvitationLink', () => {
  it.each(['#', '?'])('reads %s parameters and decodes the address once', (separator) => {
    expect(
      readInvitationLink(
        `${SIGNUP}${separator}invitation=tok-123&email=ann%2Brun%25club%40example.com`,
      ),
    ).toEqual({ invitationToken: 'tok-123', email: 'ann+run%club@example.com' });
  });

  it('prefers the fragment and does not mix its values with the query', () => {
    expect(
      readInvitationLink(`${SIGNUP}?invitation=old&email=old%40example.com#invitation=new`),
    ).toEqual({ invitationToken: 'new', email: '' });
  });

  it('does not fall back to a query token when the fragment token is empty', () => {
    expect(readInvitationLink(`${SIGNUP}?invitation=old#invitation=`)).toEqual({
      invitationToken: '',
      email: '',
    });
  });

  it('accepts legacy query links with an unrelated fragment', () => {
    expect(readInvitationLink(`${SIGNUP}?invitation=old#details`)).toEqual({
      invitationToken: 'old',
      email: '',
    });
  });

  it.each(['', '#email=ann%40example.com', '?email=ann%40example.com', '#invitation=%20%20'])(
    'returns an empty token when no token is present: %s',
    (suffix) => {
      expect(readInvitationLink(SIGNUP + suffix).invitationToken).toBe('');
    },
  );

  it('trims surrounding whitespace without decoding percent sequences twice', () => {
    expect(
      readInvitationLink(`${SIGNUP}#invitation=%20tok%20&email=%20ann%252Bclub%40example.com%20`),
    ).toEqual({ invitationToken: 'tok', email: 'ann%2Bclub@example.com' });
  });
});
