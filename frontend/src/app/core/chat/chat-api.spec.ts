import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { ChatApi } from './chat-api';

const URL = '/api/chat/messages/';
const ASKED = {
  id: '01a1dbcf-0000-7000-8000-000000000001',
  role: 'user',
  text: 'Rain on Saturday',
  created_at: '2026-11-14T10:00:00.123456Z',
  changes: [],
  plan: null,
};
const ANSWERED = {
  id: '01a1dbcf-0000-7000-8000-000000000002',
  role: 'coach',
  text: 'Sunday then.',
  created_at: '2026-11-14T10:00:05Z',
  changes: ['Run on Sat (60 min) moved to Sun'],
  plan: { id: '01a1dbcf-0000-7000-8000-000000000003', week_start: '2026-11-09' },
};
const NO_SESSION = { detail: 'Authentication credentials were not provided.' };

describe('ChatApi', () => {
  let api: ChatApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ChatApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    method: string,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  async function runFailing(
    action: Promise<unknown>,
    method: string,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    await expect(action).rejects.toThrow();
  }

  describe('list', () => {
    it('returns the conversation as it is', async () => {
      const { result } = await run(api.list(), 'GET', { messages: [ASKED, ANSWERED] }, 200);

      expect(result).toEqual({ kind: 'ok', messages: [ASKED, ANSWERED] });
    });

    it('returns an empty conversation', async () => {
      const { result } = await run(api.list(), 'GET', { messages: [] }, 200);

      expect(result).toEqual({ kind: 'ok', messages: [] });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.list(), 'GET', NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a body that is no object', null],
      ['messages that are no list', { messages: 'hi' }],
      ['a role that is not known', { messages: [{ ...ASKED, role: 'system' }] }],
      ['text that is empty', { messages: [{ ...ASKED, text: '' }] }],
      ['an id that is missing', { messages: [{ ...ASKED, id: undefined }] }],
      ['changes that are no list of text', { messages: [{ ...ANSWERED, changes: [3] }] }],
      ['a plan without a week', { messages: [{ ...ANSWERED, plan: { id: 'x' } }] }],
      [
        'a plan with a week that is no date',
        { messages: [{ ...ANSWERED, plan: { id: 'x', week_start: 'monday' } }] },
      ],
    ])('rejects %s', async (_name, reply) => {
      await runFailing(api.list(), 'GET', reply, 200);
    });

    it('rejects a server error', async () => {
      await runFailing(api.list(), 'GET', 'oops', 500);
    });
  });

  describe('write', () => {
    it('sends the text and returns the two messages', async () => {
      const { result, request } = await run(
        api.write('Rain on Saturday'),
        'POST',
        { messages: [ASKED, ANSWERED] },
        201,
      );

      expect(request.request.body).toEqual({ text: 'Rain on Saturday' });
      expect(result).toEqual({ kind: 'ok', messages: [ASKED, ANSWERED] });
    });

    it('returns the texts for a message that cannot be used', async () => {
      const { result } = await run(
        api.write(''),
        'POST',
        { detail: 'Write a message.', code: 'invalid', errors: ['Write a message.'] },
        400,
      );

      expect(result).toEqual({ kind: 'invalid', errors: ['Write a message.'] });
    });

    it('has a text of its own when the answer has none', async () => {
      const { result } = await run(api.write('x'), 'POST', 'Bad Request', 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['Your message could not be sent. Please check it.'],
      });
    });

    it('says when no provider is set up', async () => {
      const { result } = await run(
        api.write('x'),
        'POST',
        { detail: 'No AI provider is set up.', code: 'not_configured' },
        409,
      );

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('rejects a conflict it does not know', async () => {
      await runFailing(api.write('x'), 'POST', { code: 'other' }, 409);
    });

    it('tells the limit of this server apart from the one of the provider', async () => {
      const own = await run(api.write('x'), 'POST', { detail: 'Request was throttled.' }, 429);
      expect(own.result).toEqual({ kind: 'rate_limited' });

      const theirs = await run(
        api.write('x'),
        'POST',
        { detail: 'The provider asks to slow down.', code: 'rate_limited', retry_after: 30 },
        429,
      );
      expect(theirs.result).toEqual({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider asks to slow down.',
        retry_after: 30,
      });
    });

    it.each([
      [502, 'invalid_key', 'invalid_key'],
      [503, 'unavailable', 'unavailable'],
      [502, 'something_new', 'unexpected'],
    ])('names a provider problem (%i, %s)', async (status, code, problem) => {
      const { result } = await run(
        api.write('x'),
        'POST',
        { detail: 'The provider says no.', code },
        status,
      );

      expect(result).toMatchObject({ kind: 'provider_problem', problem });
    });

    it('uses a fixed text when a proxy answers with a page of its own', async () => {
      const { result } = await run(api.write('x'), 'POST', '<html>Bad gateway</html>', 502);

      expect(result).toEqual({
        kind: 'provider_problem',
        problem: 'unexpected',
        message: 'The AI provider could not be used right now. Please try again later.',
        retry_after: null,
      });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.write('x'), 'POST', NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.write('x'), 'POST', { messages: [{ ...ASKED, role: 'x' }] }, 201);
    });
  });

  describe('clear', () => {
    it('deletes the conversation', async () => {
      const { result } = await run(api.clear(), 'DELETE', null, 204);

      expect(result).toEqual({ kind: 'cleared' });
    });

    it('says when the session has ended', async () => {
      const { result } = await run(api.clear(), 'DELETE', NO_SESSION, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects a server error', async () => {
      await runFailing(api.clear(), 'DELETE', 'oops', 500);
    });
  });
});
