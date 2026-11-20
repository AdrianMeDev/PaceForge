import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { InvitationsApi } from './invitations-api';
import { Invitation } from './invitations-models';

const URL = '/api/admin/invitations/';
const ID = '01a1d196-94b6-7299-80f5-5e016f23dd2b';

const PENDING: Invitation = {
  id: ID,
  email: 'invitee+run@example.com',
  status: 'pending',
  created_at: '2026-11-12T21:07:49.046419Z',
  expires_at: '2026-11-19T21:07:49.046339Z',
  sent_at: null,
};
const SENT: Invitation = { ...PENDING, sent_at: '2026-11-12T21:07:50.512003Z' };

const MFA_REQUIRED = {
  detail: 'Two-factor authentication must be turned on for administrators.',
  code: 'mfa_required',
};
const PLAIN_REFUSAL = { detail: 'You do not have permission to perform this action.' };

describe('InvitationsApi', () => {
  let api: InvitationsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(InvitationsApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    method: string,
    url: string,
    reply: string | object,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  describe('list', () => {
    it('returns the invitations as the server lists them', async () => {
      const used: Invitation = { ...PENDING, id: 'other', status: 'used' };

      const { result } = await run(api.list(), 'GET', URL, [used, PENDING], 200);

      expect(result).toEqual({ kind: 'ok', invitations: [used, PENDING] });
    });

    it('returns an empty list', async () => {
      const { result } = await run(api.list(), 'GET', URL, [], 200);

      expect(result).toEqual({ kind: 'ok', invitations: [] });
    });

    it('keeps the time the invitation mail was sent, or null before any mail', async () => {
      const { result } = await run(api.list(), 'GET', URL, [SENT, PENDING], 200);

      expect(result).toEqual({ kind: 'ok', invitations: [SENT, PENDING] });
    });

    it('tells an administrator without two-factor authentication from other refusals', async () => {
      const { result } = await run(api.list(), 'GET', URL, MFA_REQUIRED, 403);

      expect(result).toEqual({ kind: 'mfa_required' });
    });

    it.each([
      ['a refusal without a code', PLAIN_REFUSAL],
      ['a missing login', { detail: 'Authentication credentials were not provided.' }],
      ['a failed CSRF check', { detail: 'CSRF Failed: CSRF token missing.' }],
      ['a body that is not an object', 'Forbidden'],
      ['a different code', { detail: 'x', code: 'something_else' }],
    ])('treats %s as plainly forbidden', async (_label, body) => {
      const { result } = await run(api.list(), 'GET', URL, body, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.list(), 'GET', URL, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('create', () => {
    const LINK = 'http://localhost:4200/account/signup?invitation=tok&email=a%40b.de';
    const CREATED = { ...SENT, invite_url: LINK, email_sent: true };

    it('sends the email address in the body', async () => {
      const { request } = await run(api.create('invitee@example.com'), 'POST', URL, CREATED, 201);

      expect(request.request.body).toEqual({ email: 'invitee@example.com' });
    });

    it('returns the invitation and, separately, the link that is only given once', async () => {
      const { result } = await run(api.create('invitee@example.com'), 'POST', URL, CREATED, 201);

      expect(result).toEqual({
        kind: 'created',
        invitation: SENT,
        inviteUrl: LINK,
        emailSent: true,
      });
      expect(JSON.stringify(result.kind === 'created' ? result.invitation : {})).not.toContain(
        'tok',
      );
    });

    it('reports whether the invitation mail could not be delivered', async () => {
      const body = { ...PENDING, invite_url: LINK, email_sent: false };

      const { result } = await run(api.create('invitee@example.com'), 'POST', URL, body, 201);

      expect(result).toEqual({
        kind: 'created',
        invitation: PENDING,
        inviteUrl: LINK,
        emailSent: false,
      });
    });

    it('reports a rate limit when too many invitation mails were sent', async () => {
      const { result } = await run(
        api.create('invitee@example.com'),
        'POST',
        URL,
        { detail: 'Request was throttled.' },
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([
      [{ email: ['Enter a valid email address.'] }, ['Enter a valid email address.']],
      [{ email: ['This field is required.'] }, ['This field is required.']],
      [{ email: ['One.', 'Two.'], other: ['Three.'] }, ['One.', 'Two.', 'Three.']],
    ])('collects the field errors of %j', async (body, errors) => {
      const { result } = await run(api.create('x'), 'POST', URL, body, 400);

      expect(result).toEqual({ kind: 'invalid', errors });
    });

    it.each([{}, 'bad request', { email: [] }])(
      'falls back to a generic message for the 400 body %j',
      async (body) => {
        const { result } = await run(api.create('x'), 'POST', URL, body, 400);

        expect(result).toEqual({ kind: 'invalid', errors: ['The request was not accepted.'] });
      },
    );

    it('tells the two kinds of refusal apart', async () => {
      const first = await run(api.create('a@b.de'), 'POST', URL, MFA_REQUIRED, 403);
      const second = await run(api.create('a@b.de'), 'POST', URL, PLAIN_REFUSAL, 403);

      expect(first.result).toEqual({ kind: 'mfa_required' });
      expect(second.result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.create('a@b.de'), 'POST', URL, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('resend', () => {
    const RESEND = `${URL}${ID}/resend/`;
    const LINK = 'http://localhost:4200/account/signup?invitation=new&email=a%40b.de';
    const RESENT = { ...SENT, invite_url: LINK, email_sent: true };

    it('posts to the resend address of that invitation', async () => {
      const { request } = await run(api.resend(ID), 'POST', RESEND, RESENT, 200);

      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({});
    });

    it('returns the invitation with the new link and the mail result', async () => {
      const { result } = await run(api.resend(ID), 'POST', RESEND, RESENT, 200);

      expect(result).toEqual({
        kind: 'resent',
        invitation: SENT,
        inviteUrl: LINK,
        emailSent: true,
      });
    });

    it('reports a mail that could not be delivered without failing the resend', async () => {
      const body = { ...RESENT, email_sent: false };

      const { result } = await run(api.resend(ID), 'POST', RESEND, body, 200);

      expect(result).toEqual({
        kind: 'resent',
        invitation: SENT,
        inviteUrl: LINK,
        emailSent: false,
      });
    });

    it('reports an invitation that was used or revoked', async () => {
      const { result } = await run(
        api.resend(ID),
        'POST',
        RESEND,
        { detail: 'A used or revoked invitation cannot be sent again.' },
        409,
      );

      expect(result).toEqual({ kind: 'conflict' });
    });

    it('reports an unknown invitation', async () => {
      const { result } = await run(
        api.resend(ID),
        'POST',
        RESEND,
        { detail: 'No UserInvitation matches the given query.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('reports a rate limit', async () => {
      const { result } = await run(
        api.resend(ID),
        'POST',
        RESEND,
        { detail: 'Request was throttled.' },
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it('tells the two kinds of refusal apart', async () => {
      const first = await run(api.resend(ID), 'POST', RESEND, MFA_REQUIRED, 403);
      const second = await run(api.resend(ID), 'POST', RESEND, PLAIN_REFUSAL, 403);

      expect(first.result).toEqual({ kind: 'mfa_required' });
      expect(second.result).toEqual({ kind: 'forbidden' });
    });

    it('keeps odd characters of an id out of the address', async () => {
      const weird = '../../x?y=1';
      const { request } = await run(
        api.resend(weird),
        'POST',
        `${URL}${encodeURIComponent(weird)}/resend/`,
        { detail: 'nope' },
        404,
      );

      expect(request.request.url).not.toContain('../');
      expect(request.request.url).not.toContain('?');
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.resend(ID), 'POST', RESEND, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('revoke', () => {
    const REVOKE = `${URL}${ID}/revoke/`;

    it('posts to the revoke address of that invitation', async () => {
      const { request } = await run(
        api.revoke(ID),
        'POST',
        REVOKE,
        { ...PENDING, status: 'revoked' },
        200,
      );

      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({});
    });

    it('returns the revoked invitation', async () => {
      const revoked: Invitation = { ...PENDING, status: 'revoked' };

      const { result } = await run(api.revoke(ID), 'POST', REVOKE, revoked, 200);

      expect(result).toEqual({ kind: 'revoked', invitation: revoked });
    });

    it('reports an invitation that was used already', async () => {
      const { result } = await run(
        api.revoke(ID),
        'POST',
        REVOKE,
        { detail: 'A used invitation cannot be revoked.' },
        409,
      );

      expect(result).toEqual({ kind: 'conflict' });
    });

    it('reports an unknown invitation', async () => {
      const { result } = await run(
        api.revoke(ID),
        'POST',
        REVOKE,
        { detail: 'No UserInvitation matches the given query.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('tells the two kinds of refusal apart', async () => {
      const first = await run(api.revoke(ID), 'POST', REVOKE, MFA_REQUIRED, 403);
      const second = await run(api.revoke(ID), 'POST', REVOKE, PLAIN_REFUSAL, 403);

      expect(first.result).toEqual({ kind: 'mfa_required' });
      expect(second.result).toEqual({ kind: 'forbidden' });
    });

    it('keeps odd characters of an id out of the address', async () => {
      const weird = '../../x?y=1';
      const { request } = await run(
        api.revoke(weird),
        'POST',
        `${URL}${encodeURIComponent(weird)}/revoke/`,
        { detail: 'nope' },
        404,
      );

      expect(request.request.url).not.toContain('../');
      expect(request.request.url).not.toContain('?');
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.revoke(ID), 'POST', REVOKE, 'boom', 500)).rejects.toBeDefined();
    });
  });
});
