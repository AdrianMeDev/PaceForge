import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { CoachApi } from './coach-api';
import {
  AiCostsState,
  AiProviderInput,
  AiProviderState,
  CheckOutcome,
  ModelPriceInput,
} from './coach-models';

const URL = '/api/coach/provider/';
const CHECK_URL = '/api/coach/provider/check/';
const KEY = 'sk-ant-replay-0123456789-notreal';
const FAKE_ADDRESS = 'http://127.0.0.1:8031/v1';

// The shapes are those of the real API (replayed with curl against a real Django).
const USAGE_NONE = {
  calls: 0,
  input_tokens: 0,
  output_tokens: 0,
  cache_read_tokens: 0,
  cache_write_tokens: 0,
  days: 30,
};
const NOT_SET_UP = {
  configured: false,
  provider: null,
  model: '',
  season_model: '',
  week_model: '',
  chat_model: '',
  base_url: null,
  has_key: false,
  status: null,
  last_checked_at: null,
  last_success_at: null,
  allowed_base_urls: [FAKE_ADDRESS],
  usage: USAGE_NONE,
};
const ANTHROPIC = {
  ...NOT_SET_UP,
  configured: true,
  provider: 'anthropic',
  model: 'claude-sonnet-5-5',
  has_key: true,
  status: 'untested',
};
const CONNECTED = {
  ...ANTHROPIC,
  status: 'connected',
  last_checked_at: '2026-11-13T18:20:30.879214Z',
  last_success_at: '2026-11-13T18:20:30.879214Z',
  usage: {
    calls: 1,
    input_tokens: 9,
    output_tokens: 2,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    days: 30,
  },
};
const COMPATIBLE = {
  ...NOT_SET_UP,
  configured: true,
  provider: 'openai_compatible',
  model: 'llama3.1:8b',
  base_url: FAKE_ADDRESS,
  status: 'untested',
};
const CHECK_OK = { ok: true, problem: null, message: '', retry_after: null };
const CHECK_REFUSED = {
  ok: false,
  problem: 'invalid_key',
  message: 'The provider did not accept the key. Check that you copied all of it.',
  retry_after: null,
};
const CHECK_SLOW = {
  ok: false,
  problem: 'rate_limited',
  message: 'The provider is asking to slow down. Please try again in a moment.',
  retry_after: 30,
};

const COSTS_URL = '/api/coach/costs/';
const PRICES_URL = '/api/coach/costs/prices/';
const COSTS = {
  prices: [
    {
      id: 7,
      model: 'claude-sonnet-5-5',
      input_per_million: '3.0000',
      output_per_million: '15.0000',
      cached_per_million: null,
    },
  ],
  months: [
    {
      month: '2026-11',
      calls: 3,
      input_tokens: 1000,
      output_tokens: 200,
      cache_read_tokens: 100,
      cache_write_tokens: 50,
      cost: '0.0060',
      unpriced_models: ['llama3.1:8b'],
    },
    {
      month: '2026-10',
      calls: 0,
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      cost: null,
      unpriced_models: [],
    },
  ],
};

const NO_SESSION = { detail: 'Authentication credentials were not provided.' };

const REMOVE = Symbol('remove');
type Edit = [path: (string | number)[], value: unknown];

/** A copy of the real answer with places changed or removed, for the answers of the wrong shape. */
function altered(source: object, ...edits: Edit[]): unknown {
  const copy = structuredClone(source) as unknown;
  for (const [path, value] of edits) {
    const parent = path
      .slice(0, -1)
      .reduce<unknown>((node, key) => (node as Record<string | number, unknown>)[key], copy);
    const last = path[path.length - 1];
    if (value === REMOVE) {
      delete (parent as Record<string | number, unknown>)[last];
    } else {
      (parent as Record<string | number, unknown>)[last] = value;
    }
  }
  return copy;
}

describe('CoachApi', () => {
  let api: CoachApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(CoachApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    method: string,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  /** The call must fail, and fail with a rejection rather than with a value. */
  async function runFailing(
    action: Promise<unknown>,
    method: string,
    url: string,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === method && req.url === url),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    await expect(action).rejects.toThrow();
  }

  const WRONG_STATES: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'state'],
    ['no configured flag', altered(ANTHROPIC, [['configured'], REMOVE])],
    ['a text as configured flag', altered(ANTHROPIC, [['configured'], 'yes'])],
    ['an unknown provider', altered(ANTHROPIC, [['provider'], 'gemini'])],
    ['no provider', altered(ANTHROPIC, [['provider'], REMOVE])],
    ['a number as provider', altered(ANTHROPIC, [['provider'], 5])],
    ['no model', altered(ANTHROPIC, [['model'], REMOVE])],
    ['null as model', altered(ANTHROPIC, [['model'], null])],
    ['no season model', altered(ANTHROPIC, [['season_model'], REMOVE])],
    ['null as season model', altered(ANTHROPIC, [['season_model'], null])],
    ['no week model', altered(ANTHROPIC, [['week_model'], REMOVE])],
    ['null as week model', altered(ANTHROPIC, [['week_model'], null])],
    ['no chat model', altered(ANTHROPIC, [['chat_model'], REMOVE])],
    ['a number as chat model', altered(ANTHROPIC, [['chat_model'], 5])],
    ['a number as address', altered(COMPATIBLE, [['base_url'], 5])],
    ['no key flag', altered(ANTHROPIC, [['has_key'], REMOVE])],
    ['a text as key flag', altered(ANTHROPIC, [['has_key'], 'true'])],
    ['an unknown status', altered(ANTHROPIC, [['status'], 'broken'])],
    ['no status', altered(ANTHROPIC, [['status'], REMOVE])],
    ['a time that is no time', altered(CONNECTED, [['last_checked_at'], 'yesterday'])],
    ['a number as time', altered(CONNECTED, [['last_success_at'], 5])],
    ['no list of addresses', altered(ANTHROPIC, [['allowed_base_urls'], REMOVE])],
    ['an object as list of addresses', altered(ANTHROPIC, [['allowed_base_urls'], {}])],
    [
      'a number among the addresses',
      altered(ANTHROPIC, [['allowed_base_urls'], [FAKE_ADDRESS, 5]]),
    ],
    ['no usage', altered(ANTHROPIC, [['usage'], REMOVE])],
    ['a list as usage', altered(ANTHROPIC, [['usage'], []])],
    ['no calls', altered(ANTHROPIC, [['usage', 'calls'], REMOVE])],
    ['a text as calls', altered(ANTHROPIC, [['usage', 'calls'], '1'])],
    ['a fraction as input tokens', altered(ANTHROPIC, [['usage', 'input_tokens'], 1.5])],
    ['negative output tokens', altered(ANTHROPIC, [['usage', 'output_tokens'], -1])],
    ['no cached read count', altered(ANTHROPIC, [['usage', 'cache_read_tokens'], REMOVE])],
    ['no cached write count', altered(ANTHROPIC, [['usage', 'cache_write_tokens'], REMOVE])],
    ['a fractional cached read count', altered(ANTHROPIC, [['usage', 'cache_read_tokens'], 1.5])],
    ['negative cached writes', altered(ANTHROPIC, [['usage', 'cache_write_tokens'], -1])],
    ['a text as cached reads', altered(ANTHROPIC, [['usage', 'cache_read_tokens'], '5'])],
    [
      'more cached tokens than input',
      altered(ANTHROPIC, [['usage', 'cache_read_tokens'], 8], [['usage', 'cache_write_tokens'], 2]),
    ],
    ['no days', altered(ANTHROPIC, [['usage', 'days'], REMOVE])],
    ['zero days', altered(ANTHROPIC, [['usage', 'days'], 0])],
    ['a setup without a provider', altered(ANTHROPIC, [['provider'], null])],
    ['a setup without a status', altered(ANTHROPIC, [['status'], null])],
    ['a provider without a setup', altered(NOT_SET_UP, [['provider'], 'anthropic'])],
    ['a status without a setup', altered(NOT_SET_UP, [['status'], 'connected'])],
  ];

  const WRONG_CHECKS: [string, unknown][] = [
    ['no check', altered({ ...CONNECTED, check: CHECK_OK }, [['check'], REMOVE])],
    ['a list as check', { ...CONNECTED, check: [] }],
    ['a text as check', { ...CONNECTED, check: 'ok' }],
    ['no ok flag', { ...CONNECTED, check: altered(CHECK_OK, [['ok'], REMOVE]) }],
    ['a text as ok flag', { ...CONNECTED, check: altered(CHECK_OK, [['ok'], 'true']) }],
    ['an unknown problem', { ...CONNECTED, check: altered(CHECK_REFUSED, [['problem'], 'weird']) }],
    ['no problem', { ...CONNECTED, check: altered(CHECK_OK, [['problem'], REMOVE]) }],
    ['a success with a problem', { ...CONNECTED, check: { ...CHECK_OK, problem: 'unexpected' } }],
    ['a failure without a problem', { ...CONNECTED, check: { ...CHECK_OK, ok: false } }],
    ['no message', { ...CONNECTED, check: altered(CHECK_REFUSED, [['message'], REMOVE]) }],
    ['a number as message', { ...CONNECTED, check: altered(CHECK_REFUSED, [['message'], 5]) }],
    ['a text as wait', { ...CONNECTED, check: altered(CHECK_SLOW, [['retry_after'], '30']) }],
    ['a fraction as wait', { ...CONNECTED, check: altered(CHECK_SLOW, [['retry_after'], 1.5]) }],
    ['a negative wait', { ...CONNECTED, check: altered(CHECK_SLOW, [['retry_after'], -1]) }],
    ['no wait', { ...CONNECTED, check: altered(CHECK_SLOW, [['retry_after'], REMOVE]) }],
  ];

  describe('get', () => {
    it('returns a user who has not set anything up', async () => {
      const { result, request } = await run(api.get(), 'GET', URL, NOT_SET_UP, 200);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'ok', state: NOT_SET_UP as AiProviderState });
    });

    it('reads the cached tokens of the usage', async () => {
      const cached = altered(
        CONNECTED,
        [['usage', 'input_tokens'], 3420],
        [['usage', 'cache_read_tokens'], 3000],
        [['usage', 'cache_write_tokens'], 400],
      );

      const { result } = await run(api.get(), 'GET', URL, cached as object, 200);

      expect(result).toMatchObject({
        state: { usage: { input_tokens: 3420, cache_read_tokens: 3000, cache_write_tokens: 400 } },
      });
    });

    it('takes the cached tokens that make up the whole input', async () => {
      const all = altered(
        CONNECTED,
        [['usage', 'input_tokens'], 10],
        [['usage', 'cache_read_tokens'], 6],
        [['usage', 'cache_write_tokens'], 4],
      );

      const { result } = await run(api.get(), 'GET', URL, all as object, 200);

      expect(result).toMatchObject({ kind: 'ok' });
    });

    it('returns a setup with its status, times and usage', async () => {
      const { result } = await run(api.get(), 'GET', URL, CONNECTED, 200);

      expect(result).toEqual({ kind: 'ok', state: CONNECTED as AiProviderState });
    });

    it('returns an OpenAI-compatible setup with its address and without a key', async () => {
      const { result } = await run(api.get(), 'GET', URL, COMPATIBLE, 200);

      expect(result).toMatchObject({
        state: { provider: 'openai_compatible', base_url: FAKE_ADDRESS, has_key: false },
      });
    });

    it.each(['untested', 'connected', 'invalid', 'unavailable'])(
      'knows the status %s',
      async (status) => {
        const { result } = await run(api.get(), 'GET', URL, { ...ANTHROPIC, status }, 200);

        expect(result).toMatchObject({ state: { status } });
      },
    );

    it('takes over only the known fields and never a key', async () => {
      const crowded = altered(
        ANTHROPIC,
        [['api_key'], KEY],
        [['owner'], 'x'],
        [['usage', 'secret'], 1],
      );

      const { result } = await run(api.get(), 'GET', URL, crowded as object, 200);

      expect(result).toEqual({ kind: 'ok', state: ANTHROPIC });
      expect(JSON.stringify(result)).not.toContain(KEY);
    });

    it('copies the list of addresses', async () => {
      const body = altered(ANTHROPIC);

      const { result } = await run(api.get(), 'GET', URL, body as object, 200);

      const copy = result.kind === 'ok' ? result.state.allowed_base_urls : null;
      expect(copy).not.toBe((body as { allowed_base_urls: string[] }).allowed_base_urls);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.get(), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_STATES)('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.get(), 'GET', URL, bad as object | null, 200);
    });

    it.each([404, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.get(), 'GET', URL, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.get();
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === URL));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });

  describe('save', () => {
    const WITH_KEY: AiProviderInput = {
      provider: 'anthropic',
      model: 'claude-sonnet-5-5',
      api_key: KEY,
    };

    it('puts the input as it is and returns the setup', async () => {
      const { result, request } = await run(api.save(WITH_KEY), 'PUT', URL, ANTHROPIC, 200);

      expect(request.request.body).toEqual(WITH_KEY);
      expect(result).toEqual({ kind: 'ok', state: ANTHROPIC });
    });

    it('does not read the key back from the answer', async () => {
      const echoing = altered(ANTHROPIC, [['api_key'], KEY]);

      const { result } = await run(api.save(WITH_KEY), 'PUT', URL, echoing as object, 200);

      expect(JSON.stringify(result)).not.toContain(KEY);
    });

    it('leaves the key out to keep the stored one', async () => {
      const input: AiProviderInput = {
        provider: 'anthropic',
        model: 'claude-opus-5-5',
        season_model: '',
      };

      const { request } = await run(api.save(input), 'PUT', URL, ANTHROPIC, 200);

      expect(request.request.body).toEqual(input);
      expect(Object.keys(request.request.body as object)).not.toContain('api_key');
    });

    it('sends an empty key as an empty text and an address for a compatible endpoint', async () => {
      const input: AiProviderInput = {
        provider: 'openai_compatible',
        model: 'llama3.1:8b',
        base_url: FAKE_ADDRESS,
        api_key: '',
      };

      const { result, request } = await run(api.save(input), 'PUT', URL, COMPATIBLE, 200);

      expect(request.request.body).toEqual(input);
      expect(result).toMatchObject({ kind: 'ok', state: { provider: 'openai_compatible' } });
    });

    it('returns the messages by field and as one list', async () => {
      const { result } = await run(
        api.save(WITH_KEY),
        'PUT',
        URL,
        {
          model: ['Enter a model name.'],
          api_key: ['A key has no spaces or special characters and at most 500 characters.'],
        },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [
          'Enter a model name.',
          'A key has no spaces or special characters and at most 500 characters.',
        ],
        fields: {
          model: ['Enter a model name.'],
          api_key: ['A key has no spaces or special characters and at most 500 characters.'],
        },
      });
    });

    it('keeps the message about an address that is not allowed', async () => {
      const { result } = await run(
        api.save(WITH_KEY),
        'PUT',
        URL,
        { base_url: ['This address is not allowed on this server.'] },
        400,
      );

      expect(result).toMatchObject({
        fields: { base_url: ['This address is not allowed on this server.'] },
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
      ['a list', ['x']],
      ['messages that are no text', { model: [5, null] }],
    ])('uses a fixed message for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.save(WITH_KEY), 'PUT', URL, reply, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.save(WITH_KEY), 'PUT', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_STATES)('rejects a saved answer with %s', async (_name, bad) => {
      await runFailing(api.save(WITH_KEY), 'PUT', URL, bad as object | null, 200);
    });

    it.each([201, 404, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.save(WITH_KEY), 'PUT', URL, 'oops', status);
    });
  });

  describe('remove', () => {
    it('removes the setup', async () => {
      const { result, request } = await run(api.remove(), 'DELETE', URL, null, 204);

      expect(request.request.body).toBeNull();
      expect(result).toEqual({ kind: 'removed' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.remove(), 'DELETE', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([200, 400, 404, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.remove(), 'DELETE', URL, 'oops', status);
    });
  });

  describe('check', () => {
    it('posts to the check address and returns the setup with the outcome', async () => {
      const { result, request } = await run(
        api.check(),
        'POST',
        CHECK_URL,
        { ...CONNECTED, check: CHECK_OK },
        200,
      );

      expect(request.request.body).toEqual({});
      expect(result).toEqual({
        kind: 'checked',
        state: CONNECTED as AiProviderState,
        check: CHECK_OK as CheckOutcome,
      });
    });

    it('returns a refused key as an outcome, not as a failure', async () => {
      const { result } = await run(
        api.check(),
        'POST',
        CHECK_URL,
        { ...CONNECTED, status: 'invalid', check: CHECK_REFUSED },
        200,
      );

      expect(result).toMatchObject({
        kind: 'checked',
        state: { status: 'invalid' },
        check: CHECK_REFUSED,
      });
    });

    it('returns how long the provider asked to wait', async () => {
      const { result } = await run(
        api.check(),
        'POST',
        CHECK_URL,
        { ...CONNECTED, check: CHECK_SLOW },
        200,
      );

      expect(result).toMatchObject({ check: { problem: 'rate_limited', retry_after: 30 } });
    });

    it.each(['invalid_key', 'rate_limited', 'unavailable', 'unexpected', 'not_allowed'])(
      'knows the problem %s',
      async (problem) => {
        const { result } = await run(
          api.check(),
          'POST',
          CHECK_URL,
          { ...CONNECTED, check: { ok: false, problem, message: 'Text.', retry_after: null } },
          200,
        );

        expect(result).toMatchObject({ check: { ok: false, problem, message: 'Text.' } });
      },
    );

    it('takes over only the known fields and never a key', async () => {
      const crowded = {
        ...CONNECTED,
        api_key: KEY,
        check: { ...CHECK_OK, provider_text: KEY },
      };

      const { result } = await run(api.check(), 'POST', CHECK_URL, crowded, 200);

      expect(JSON.stringify(result)).not.toContain(KEY);
    });

    it('says when nothing is set up', async () => {
      const { result } = await run(
        api.check(),
        'POST',
        CHECK_URL,
        { detail: 'No AI provider is set up.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_configured' });
    });

    it('says when there were too many checks', async () => {
      const { result } = await run(
        api.check(),
        'POST',
        CHECK_URL,
        { detail: 'Request was throttled. Expected available in 60 seconds.' },
        429,
      );

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.check(), 'POST', CHECK_URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['no body', null],
      ['a list as body', []],
      ['a text as body', 'checked'],
    ])('rejects a checked answer with %s', async (_name, bad) => {
      await runFailing(api.check(), 'POST', CHECK_URL, bad as object | null, 200);
    });

    it.each(
      WRONG_STATES.filter(
        ([, bad]) => typeof bad === 'object' && bad !== null && !Array.isArray(bad),
      ),
    )('rejects a checked answer whose setup has %s', async (_name, bad) => {
      const body = { ...(bad as object), check: CHECK_OK };

      await runFailing(api.check(), 'POST', CHECK_URL, body, 200);
    });

    it.each(WRONG_CHECKS)('rejects a checked answer with %s', async (_name, bad) => {
      await runFailing(api.check(), 'POST', CHECK_URL, bad as object | null, 200);
    });

    it.each([201, 400, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.check(), 'POST', CHECK_URL, 'oops', status);
    });
  });
  describe('costs', () => {
    const WRONG_COSTS: [string, unknown][] = [
      ['no body', null],
      ['a list as body', []],
      ['no prices', altered(COSTS, [['prices'], REMOVE])],
      ['an object as prices', altered(COSTS, [['prices'], {}])],
      ['no months', altered(COSTS, [['months'], REMOVE])],
      ['a price without id', altered(COSTS, [['prices', 0, 'id'], REMOVE])],
      ['a text as price id', altered(COSTS, [['prices', 0, 'id'], '7'])],
      ['an empty model name', altered(COSTS, [['prices', 0, 'model'], ''])],
      ['a number as input price', altered(COSTS, [['prices', 0, 'input_per_million'], 3])],
      ['a text that is no price', altered(COSTS, [['prices', 0, 'output_per_million'], 'free'])],
      ['a negative price', altered(COSTS, [['prices', 0, 'input_per_million'], '-3.0000'])],
      ['no cached price', altered(COSTS, [['prices', 0, 'cached_per_million'], REMOVE])],
      ['a number as cached price', altered(COSTS, [['prices', 0, 'cached_per_million'], 1])],
      ['a month that is no month', altered(COSTS, [['months', 0, 'month'], 'November'])],
      ['month thirteen', altered(COSTS, [['months', 0, 'month'], '2026-13'])],
      ['a fraction as calls', altered(COSTS, [['months', 0, 'calls'], 1.5])],
      ['negative output tokens', altered(COSTS, [['months', 0, 'output_tokens'], -1])],
      ['no cached read count', altered(COSTS, [['months', 0, 'cache_read_tokens'], REMOVE])],
      ['more cached tokens than input', altered(COSTS, [['months', 0, 'cache_read_tokens'], 990])],
      ['a number as cost', altered(COSTS, [['months', 0, 'cost'], 0.006])],
      ['no cost', altered(COSTS, [['months', 0, 'cost'], REMOVE])],
      ['no unpriced models', altered(COSTS, [['months', 0, 'unpriced_models'], REMOVE])],
      ['a number among unpriced models', altered(COSTS, [['months', 0, 'unpriced_models'], [5]])],
    ];

    it('gets the prices and the months', async () => {
      const { result } = await run(api.getCosts(), 'GET', COSTS_URL, COSTS, 200);

      expect(result).toEqual({ kind: 'ok', state: COSTS satisfies AiCostsState });
    });

    it('takes over the known fields only', async () => {
      const extra = altered(COSTS, [['prices', 0, 'api_key'], KEY], [['secret'], 'x']);

      const { result } = await run(api.getCosts(), 'GET', COSTS_URL, extra as object, 200);

      expect(result).toEqual({ kind: 'ok', state: COSTS });
    });

    it.each(WRONG_COSTS)('rejects an answer with %s', async (_name, reply) => {
      await runFailing(api.getCosts(), 'GET', COSTS_URL, reply as object | null, 200);
    });

    it.each([401, 403])('returns forbidden for status %s', async (status) => {
      const { result } = await run(api.getCosts(), 'GET', COSTS_URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects other server errors', async () => {
      await runFailing(api.getCosts(), 'GET', COSTS_URL, 'boom', 500);
    });

    describe('savePrice', () => {
      const INPUT: ModelPriceInput = {
        model: 'claude-sonnet-5-5',
        input_per_million: 3,
        output_per_million: 15,
        cached_per_million: null,
      };

      it('puts the price as it is and returns the costs', async () => {
        const { result, request } = await run(api.savePrice(INPUT), 'PUT', PRICES_URL, COSTS, 200);

        expect(request.request.body).toEqual(INPUT);
        expect(result).toEqual({ kind: 'ok', state: COSTS });
      });

      it('returns the messages by field', async () => {
        const { result } = await run(
          api.savePrice(INPUT),
          'PUT',
          PRICES_URL,
          { input_per_million: ['Enter a price from 0 to 100000.'] },
          400,
        );

        expect(result).toEqual({
          kind: 'invalid',
          errors: ['Enter a price from 0 to 100000.'],
          fields: { input_per_million: ['Enter a price from 0 to 100000.'] },
        });
      });

      it('rejects an answer of the wrong shape', async () => {
        await runFailing(api.savePrice(INPUT), 'PUT', PRICES_URL, { prices: [] }, 200);
      });

      it.each([401, 403])('returns forbidden for status %s', async (status) => {
        const { result } = await run(api.savePrice(INPUT), 'PUT', PRICES_URL, NO_SESSION, status);

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it('rejects other server errors', async () => {
        await runFailing(api.savePrice(INPUT), 'PUT', PRICES_URL, 'boom', 500);
      });
    });

    describe('deletePrice', () => {
      const URL_7 = `${PRICES_URL}7/`;

      it('deletes one price', async () => {
        const { result } = await run(api.deletePrice(7), 'DELETE', URL_7, null, 204);

        expect(result).toEqual({ kind: 'deleted' });
      });

      it('says when the price does not exist', async () => {
        const { result } = await run(
          api.deletePrice(7),
          'DELETE',
          URL_7,
          { detail: 'Not found.' },
          404,
        );

        expect(result).toEqual({ kind: 'not_found' });
      });

      it.each([401, 403])('returns forbidden for status %s', async (status) => {
        const { result } = await run(api.deletePrice(7), 'DELETE', URL_7, NO_SESSION, status);

        expect(result).toEqual({ kind: 'forbidden' });
      });

      it('rejects other server errors', async () => {
        await runFailing(api.deletePrice(7), 'DELETE', URL_7, 'boom', 500);
      });
    });
  });
});
