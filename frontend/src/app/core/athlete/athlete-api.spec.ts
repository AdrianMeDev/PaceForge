import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { AthleteApi } from './athlete-api';
import { AthleteProfile } from './athlete-models';

const URL = '/api/athlete/';
const SYNC = `${URL}sync/`;
const FTP = `${URL}thresholds/ride/ftp/`;
const PACE = `${URL}thresholds/run/threshold_pace/`;

// The shapes are those of the real API (replayed with curl against a real Django).
const stamp = (n: number) => `2026-11-13T10:18:41.${n}Z`;
const manual = (value: number, n: number) => ({
  value,
  source: 'manual',
  basis: '',
  updated_at: stamp(n),
});
const threshold = (value: ReturnType<typeof manual> | null) => ({
  effective: value,
  candidates: value ? [value] : [],
});
const zone = (
  number: number,
  name: string,
  lower: number | null,
  upper: number | null,
  unit: string,
) => ({
  number,
  name,
  lower,
  upper,
  unit,
});

const BODY = {
  birth_year: 1985,
  sex: 'female',
  weight_kg: 61.5,
  resting_hr: 48,
  training_years: { running: 12, cycling: 3, swimming: null, strength: 0 },
  strength_experience: 'beginner',
  strength_equipment: ['gym', 'dumbbells'],
};
const NO_BODY = {
  birth_year: null,
  sex: null,
  weight_kg: null,
  resting_hr: null,
  training_years: { running: null, cycling: null, swimming: null, strength: null },
  strength_experience: null,
  strength_equipment: [],
};

const RAW = {
  ...BODY,
  timezone: 'Europe/Berlin',
  intervals: { connected: false, synced_at: null },
  sports: {
    ride: {
      thresholds: {
        ftp: threshold(manual(250, 568923)),
        lthr: threshold(manual(165, 612873)),
        max_hr: threshold(manual(190, 592165)),
      },
      zones: {
        power: {
          basis: 'ftp',
          zones: [
            zone(1, 'Active recovery', null, 138, 'W'),
            zone(2, 'Endurance', 138, 188, 'W'),
            zone(7, 'Neuromuscular power', 375, null, 'W'),
          ],
        },
        heart_rate: {
          basis: 'lthr',
          zones: [
            zone(1, 'Recovery', null, 140, 'bpm'),
            zone(5, 'Super-threshold', 165, null, 'bpm'),
          ],
        },
      },
    },
    run: {
      thresholds: {
        threshold_pace: threshold(manual(300, 633458)),
        lthr: threshold(null),
        max_hr: threshold(null),
      },
      zones: {
        pace: {
          basis: 'threshold_pace',
          zones: [zone(1, 'Recovery', 387, null, 's/km'), zone(5, 'Interval', null, 297, 's/km')],
        },
        heart_rate: null,
      },
    },
  },
};
const PROFILE = RAW as unknown as AthleteProfile;

const EMPTY = {
  ...NO_BODY,
  timezone: '',
  intervals: { connected: false, synced_at: null },
  sports: {
    ride: {
      thresholds: { ftp: threshold(null), lthr: threshold(null), max_hr: threshold(null) },
      zones: { power: null, heart_rate: null },
    },
    run: {
      thresholds: {
        threshold_pace: threshold(null),
        lthr: threshold(null),
        max_hr: threshold(null),
      },
      zones: { pace: null, heart_rate: null },
    },
  },
};

const NO_SESSION = { detail: 'Authentication credentials were not provided.' };
const THROTTLED = { detail: 'Request was throttled. Expected available in 60 seconds.' };

const REMOVE = Symbol('remove');
const FTP_PATH: (string | number)[] = ['sports', 'ride', 'thresholds', 'ftp'];
const POWER_PATH: (string | number)[] = ['sports', 'ride', 'zones', 'power'];
type Edit = [path: (string | number)[], value: unknown];

/** A copy of the real answer with places changed or removed, for the answers of the wrong shape. */
function altered(...edits: Edit[]): unknown {
  const copy = structuredClone(RAW) as unknown;
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

describe('AthleteApi', () => {
  let api: AthleteApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(AthleteApi);
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

  const WRONG_SHAPES: [string, unknown][] = [
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'profile'],
    ['no time zone', altered([['timezone'], REMOVE])],
    ['a number as time zone', altered([['timezone'], 5])],
    ['no intervals part', altered([['intervals'], REMOVE])],
    ['a text as connected', altered([['intervals', 'connected'], 'yes'])],
    ['a number as synced_at', altered([['intervals', 'synced_at'], 5])],
    ['no sports', altered([['sports'], REMOVE])],
    ['no cycling', altered([['sports', 'ride'], REMOVE])],
    ['no running', altered([['sports', 'run'], REMOVE])],
    ['no thresholds', altered([['sports', 'ride', 'thresholds'], REMOVE])],
    ['no ftp', altered([['sports', 'ride', 'thresholds', 'ftp'], REMOVE])],
    ['no pace', altered([['sports', 'run', 'thresholds', 'threshold_pace'], REMOVE])],
    ['candidates that are no list', altered([FTP_PATH.concat('candidates'), {}])],
    ['an unknown source', altered([FTP_PATH.concat('effective', 'source'), 'coach'])],
    ['a text as value', altered([FTP_PATH.concat('effective', 'value'), '250'])],
    ['not a number as value', altered([FTP_PATH.concat('effective', 'value'), NaN])],
    ['infinity as value', altered([FTP_PATH.concat('effective', 'value'), Infinity])],
    ['no basis', altered([FTP_PATH.concat('effective', 'basis'), REMOVE])],
    ['no time of change', altered([FTP_PATH.concat('candidates', 0, 'updated_at'), REMOVE])],
    ['an unknown zone basis', altered([POWER_PATH.concat('basis'), 'vo2max'])],
    ['zones that are no list', altered([POWER_PATH.concat('zones'), 'many'])],
    ['an unknown zone unit', altered([POWER_PATH.concat('zones', 0, 'unit'), 'km'])],
    ['a fraction as zone number', altered([POWER_PATH.concat('zones', 0, 'number'), 1.5])],
    ['a text as zone limit', altered([POWER_PATH.concat('zones', 0, 'upper'), 'high'])],
    ['a zone without a name', altered([POWER_PATH.concat('zones', 0, 'name'), REMOVE])],
  ];

  describe('get', () => {
    it('returns the profile', async () => {
      const { result, request } = await run(api.get(), 'GET', URL, RAW, 200);

      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
      expect(request.request.body).toBeNull();
    });

    it('returns an empty profile with nulls where nothing exists', async () => {
      const { result } = await run(api.get(), 'GET', URL, EMPTY, 200);

      expect(result).toMatchObject({
        kind: 'ok',
        profile: {
          timezone: '',
          sports: {
            ride: { thresholds: { ftp: { effective: null, candidates: [] } } },
            run: { zones: { pace: null, heart_rate: null } },
          },
        },
      });
    });

    it('keeps all candidates in the order the server sent them', async () => {
      const effective = RAW.sports.ride.thresholds.ftp.effective;
      const reply = altered([
        FTP_PATH.concat('candidates'),
        [
          effective,
          {
            value: 262,
            source: 'intervals',
            basis: 'Read from your Intervals.icu sport settings',
            updated_at: stamp(1),
          },
          { value: 241, source: 'estimated', basis: 'x', updated_at: stamp(2) },
        ],
      ]);

      const { result } = await run(api.get(), 'GET', URL, reply as object, 200);

      const profile = (result as { profile: AthleteProfile }).profile;
      expect(profile.sports.ride.thresholds.ftp.candidates.map((c) => c.source)).toEqual([
        'manual',
        'intervals',
        'estimated',
      ]);
    });

    it('treats a missing zone set or limit as null', async () => {
      const reply = altered(
        [POWER_PATH, REMOVE],
        [['sports', 'ride', 'zones', 'heart_rate', 'zones', 0, 'lower'], REMOVE],
      );

      const { result } = await run(api.get(), 'GET', URL, reply as object, 200);

      const profile = (result as { profile: AthleteProfile }).profile;
      expect(profile.sports.ride.zones.power).toBeNull();
      expect(profile.sports.ride.zones.heart_rate?.zones[0].lower).toBeNull();
    });

    it('takes over only the known fields', async () => {
      const reply = altered(
        [['owner'], 'x'],
        [['intervals', 'api_key'], 'secret'],
        [['sports', 'ride', 'extra'], 1],
        [FTP_PATH.concat('id'), 7],
        [FTP_PATH.concat('effective', 'owner'), 'x'],
        [POWER_PATH.concat('zones', 0, 'colour'), 'red'],
      );

      const { result } = await run(api.get(), 'GET', URL, reply as object, 200);

      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.get(), 'GET', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each(WRONG_SHAPES)('rejects an answer with %s', async (_name, reply) => {
      await runFailing(api.get(), 'GET', URL, reply as object | null, 200);
    });

    it.each([404, 500, 502])('rejects the unexpected status %i', async (status) => {
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

  describe('setTimezone', () => {
    it('sends the name and returns the profile', async () => {
      const { result, request } = await run(
        api.setTimezone('Europe/Berlin'),
        'PATCH',
        URL,
        RAW,
        200,
      );

      expect(request.request.body).toEqual({ timezone: 'Europe/Berlin' });
      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
    });

    it('sends an empty name to remove the time zone', async () => {
      const { result, request } = await run(api.setTimezone(''), 'PATCH', URL, EMPTY, 200);

      expect(request.request.body).toEqual({ timezone: '' });
      expect(result.kind).toBe('ok');
    });

    it('returns the messages when the name is refused', async () => {
      const { result } = await run(
        api.setTimezone('Mars/Base'),
        'PATCH',
        URL,
        { timezone: ['Enter a time zone from the IANA database, for example Europe/Berlin.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['Enter a time zone from the IANA database, for example Europe/Berlin.'],
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
      ['messages that are no text', { timezone: [5] }],
    ])('uses a fixed message for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.setTimezone('x'), 'PATCH', URL, reply, 400);

      expect(result).toEqual({ kind: 'invalid', errors: ['The input was not accepted.'] });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.setTimezone('UTC'), 'PATCH', URL, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.setTimezone('UTC'), 'PATCH', URL, { timezone: 'UTC' }, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.setTimezone('UTC'), 'PATCH', URL, 'oops', status);
    });
  });

  describe('the body and training data', () => {
    it('reads every field of them', async () => {
      const { result } = await run(api.get(), 'GET', URL, RAW, 200);

      expect(result).toMatchObject({ kind: 'ok', profile: BODY });
    });

    it('reads nothing as null and no equipment as an empty list', async () => {
      const { result } = await run(api.get(), 'GET', URL, EMPTY, 200);

      expect(result).toMatchObject({ kind: 'ok', profile: NO_BODY });
    });

    it('copies the equipment', async () => {
      const reply = altered([['strength_equipment'], ['home']]) as { strength_equipment: string[] };

      const { result } = await run(api.get(), 'GET', URL, reply, 200);

      if (result.kind !== 'ok') {
        throw new Error('expected the profile');
      }
      expect(result.profile.strength_equipment).toEqual(['home']);
      expect(result.profile.strength_equipment).not.toBe(reply.strength_equipment);
    });

    it.each([
      ['no birth year', altered([['birth_year'], REMOVE])],
      ['a text as birth year', altered([['birth_year'], '1985'])],
      ['a fractional birth year', altered([['birth_year'], 1985.5])],
      ['an unknown sex', altered([['sex'], 'x'])],
      ['no sex', altered([['sex'], REMOVE])],
      ['a text as weight', altered([['weight_kg'], '61'])],
      ['no weight', altered([['weight_kg'], REMOVE])],
      ['an infinite weight', altered([['weight_kg'], Infinity])],
      ['a fractional resting heart rate', altered([['resting_hr'], 48.5])],
      ['no resting heart rate', altered([['resting_hr'], REMOVE])],
      ['no years', altered([['training_years'], REMOVE])],
      ['a list as years', altered([['training_years'], []])],
      ['a text as years of a sport', altered([['training_years', 'running'], '12'])],
      ['fractional years of a sport', altered([['training_years', 'running'], 1.5])],
      ['no years of a sport', altered([['training_years', 'running'], REMOVE])],
      ['an unknown experience', altered([['strength_experience'], 'expert'])],
      ['no experience', altered([['strength_experience'], REMOVE])],
      ['equipment that is no list', altered([['strength_equipment'], 'gym'])],
      ['unknown equipment', altered([['strength_equipment'], ['barbell']])],
      ['equipment twice', altered([['strength_equipment'], ['gym', 'gym']])],
      ['no equipment', altered([['strength_equipment'], REMOVE])],
    ])('rejects an answer with %s', async (_name, bad) => {
      await runFailing(api.get(), 'GET', URL, bad as object, 200);
    });
  });

  describe('saveBody', () => {
    it('sends only what changes and returns the profile', async () => {
      const changes = { weight_kg: 62, sex: null, training_years: { running: 13 } };

      const { result, request } = await run(api.saveBody(changes), 'PATCH', URL, RAW, 200);

      expect(request.request.body).toEqual(changes);
      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
    });

    it('sends the equipment as given', async () => {
      const { request } = await run(
        api.saveBody({ strength_equipment: [] }),
        'PATCH',
        URL,
        RAW,
        200,
      );

      expect(request.request.body).toEqual({ strength_equipment: [] });
    });

    it('returns the messages by field and as one list', async () => {
      const refusal = {
        weight_kg: ['Enter a weight between 25 and 300 kg.'],
        resting_hr: ['Enter a resting heart rate between 25 and 120 bpm.'],
      };

      const { result } = await run(
        api.saveBody({ weight_kg: 5, resting_hr: 5 }),
        'PATCH',
        URL,
        refusal,
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: [...refusal.weight_kg, ...refusal.resting_hr],
        fields: refusal,
      });
    });

    it('keeps a message that no field owns under non_field_errors', async () => {
      const refusal = { non_field_errors: ['Send at least one field to change.'] };

      const { result } = await run(api.saveBody({}), 'PATCH', URL, refusal, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: refusal.non_field_errors,
        fields: refusal,
      });
    });

    it.each([
      ['no body', null],
      ['a text', 'Bad Request'],
      ['an empty object', {}],
      ['messages that are no text', { weight_kg: [5] }],
    ])('uses a fixed message and no fields for a refusal with %s', async (_name, reply) => {
      const { result } = await run(api.saveBody({ weight_kg: 5 }), 'PATCH', URL, reply, 400);

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(
        api.saveBody({ weight_kg: 62 }),
        'PATCH',
        URL,
        NO_SESSION,
        status,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.saveBody({ weight_kg: 62 }), 'PATCH', URL, { timezone: 'UTC' }, 200);
    });

    it.each([404, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.saveBody({ weight_kg: 62 }), 'PATCH', URL, 'oops', status);
    });
  });

  describe('setThreshold', () => {
    it('puts the value to the address of the threshold and returns the profile', async () => {
      const { result, request } = await run(
        api.setThreshold('ride', 'ftp', 250),
        'PUT',
        FTP,
        RAW,
        200,
      );

      expect(request.request.body).toEqual({ value: 250 });
      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
    });

    it('uses the address of the running pace', async () => {
      const { request } = await run(
        api.setThreshold('run', 'threshold_pace', 300),
        'PUT',
        PACE,
        RAW,
        200,
      );

      expect(request.request.body).toEqual({ value: 300 });
    });

    it('writes the sport and the metric safely into the address', async () => {
      const { request } = await run(
        api.setThreshold('ride', 'a/b?c' as never, 1),
        'PUT',
        `${URL}thresholds/ride/a%2Fb%3Fc/`,
        {},
        404,
      );

      expect(request.request.url).toBe(`${URL}thresholds/ride/a%2Fb%3Fc/`);
    });

    it('writes an odd sport safely into the address as well', async () => {
      const { request } = await run(
        api.setThreshold('x/y?z' as never, 'ftp' as never, 1),
        'PUT',
        `${URL}thresholds/x%2Fy%3Fz/ftp/`,
        {},
        404,
      );

      expect(request.request.url).toBe(`${URL}thresholds/x%2Fy%3Fz/ftp/`);
    });

    it('does not allow a metric that the sport does not have', () => {
      // @ts-expect-error cycling has no pace
      void (() => api.setThreshold('ride', 'threshold_pace', 300));
      // @ts-expect-error running has no power
      void (() => api.setThreshold('run', 'ftp', 250));
      // heart rates exist for both
      void (() => api.setThreshold('ride', 'lthr', 165));
      void (() => api.setThreshold('run', 'max_hr', 188));
    });

    it('returns the messages when the value is refused', async () => {
      const { result } = await run(
        api.setThreshold('ride', 'ftp', 5000),
        'PUT',
        FTP,
        { value: ['Enter a value between 30 and 2000 W.'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['Enter a value between 30 and 2000 W.'],
      });
    });

    it('returns all messages of a refusal', async () => {
      const { result } = await run(
        api.setThreshold('ride', 'lthr', 195),
        'PUT',
        `${URL}thresholds/ride/lthr/`,
        { value: ['Cannot be above the maximum heart rate (190 bpm).'], non_field_errors: ['x'] },
        400,
      );

      expect(result).toEqual({
        kind: 'invalid',
        errors: ['Cannot be above the maximum heart rate (190 bpm).', 'x'],
      });
    });

    it('uses a fixed message when a refusal has none', async () => {
      const { result } = await run(api.setThreshold('ride', 'ftp', 1), 'PUT', FTP, '<html>', 400);

      expect(result).toEqual({ kind: 'invalid', errors: ['The input was not accepted.'] });
    });

    it('says when the threshold does not exist', async () => {
      const { result } = await run(
        api.setThreshold('ride', 'ftp', 250),
        'PUT',
        FTP,
        { detail: 'Not found.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(
        api.setThreshold('ride', 'ftp', 250),
        'PUT',
        FTP,
        NO_SESSION,
        status,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.setThreshold('ride', 'ftp', 250), 'PUT', FTP, { value: 250 }, 200);
    });

    it.each([409, 429, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.setThreshold('ride', 'ftp', 250), 'PUT', FTP, 'oops', status);
    });
  });

  describe('clearThreshold', () => {
    it('deletes the typed value and returns the profile', async () => {
      const { result, request } = await run(
        api.clearThreshold('ride', 'ftp'),
        'DELETE',
        FTP,
        EMPTY,
        200,
      );

      expect(request.request.body).toBeNull();
      expect(result.kind).toBe('ok');
    });

    it('says when the threshold does not exist', async () => {
      const { result } = await run(
        api.clearThreshold('ride', 'ftp'),
        'DELETE',
        FTP,
        'Not found',
        404,
      );

      expect(result).toEqual({ kind: 'not_found' });
    });

    it('writes the sport and the metric safely into the address', async () => {
      const { request } = await run(
        api.clearThreshold('run', 'x/y' as never),
        'DELETE',
        `${URL}thresholds/run/x%2Fy/`,
        {},
        404,
      );

      expect(request.request.url).toBe(`${URL}thresholds/run/x%2Fy/`);
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(
        api.clearThreshold('ride', 'ftp'),
        'DELETE',
        FTP,
        NO_SESSION,
        status,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.clearThreshold('ride', 'ftp'), 'DELETE', FTP, null, 200);
    });

    it.each([204, 400, 500])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.clearThreshold('ride', 'ftp'), 'DELETE', FTP, 'oops', status);
    });
  });

  describe('syncFromIntervals', () => {
    it('posts and returns the profile', async () => {
      const { result, request } = await run(api.syncFromIntervals(), 'POST', SYNC, RAW, 200);

      expect(request.request.body).toEqual({});
      expect(result).toEqual({ kind: 'ok', profile: PROFILE });
    });

    it('says when there is no connection', async () => {
      const { result } = await run(
        api.syncFromIntervals(),
        'POST',
        SYNC,
        { detail: 'Not connected.' },
        404,
      );

      expect(result).toEqual({ kind: 'not_connected' });
    });

    it('returns the server text when Intervals.icu does not accept the stored key', async () => {
      const { result } = await run(
        api.syncFromIntervals(),
        'POST',
        SYNC,
        { detail: 'The server says: enter the key again.' },
        409,
      );

      expect(result).toEqual({
        kind: 'key_refused',
        message: 'The server says: enter the key again.',
      });
    });

    it.each([null, '<html>', {}, { detail: '' }, { detail: 5 }])(
      'uses a fixed text for a refused key without a usable message (%j)',
      async (reply) => {
        const { result } = await run(api.syncFromIntervals(), 'POST', SYNC, reply, 409);

        expect(result).toEqual({
          kind: 'key_refused',
          message:
            'Intervals.icu did not accept the stored API key. Enter it again on the Connections page.',
        });
      },
    );

    it('says when the user syncs too fast', async () => {
      const { result } = await run(api.syncFromIntervals(), 'POST', SYNC, THROTTLED, 429);

      expect(result).toEqual({ kind: 'rate_limited' });
    });

    it.each([502, 503])(
      'returns the server text when Intervals.icu is not available (%i)',
      async (status) => {
        const { result } = await run(
          api.syncFromIntervals(),
          'POST',
          SYNC,
          { detail: 'The server says: try later.' },
          status,
        );

        expect(result).toEqual({
          kind: 'unavailable',
          message: 'The server says: try later.',
        });
      },
    );

    it.each([502, 503])('uses a fixed text when %i has no usable message', async (status) => {
      const { result } = await run(api.syncFromIntervals(), 'POST', SYNC, 'Bad Gateway', status);

      expect(result).toEqual({
        kind: 'unavailable',
        message: 'Intervals.icu cannot be reached right now. Please try again later.',
      });
    });

    it.each([401, 403])('says when the session is gone (%i)', async (status) => {
      const { result } = await run(api.syncFromIntervals(), 'POST', SYNC, NO_SESSION, status);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects an answer of the wrong shape', async () => {
      await runFailing(api.syncFromIntervals(), 'POST', SYNC, { ok: true }, 200);
    });

    it.each([400, 500, 504])('rejects the unexpected status %i', async (status) => {
      await runFailing(api.syncFromIntervals(), 'POST', SYNC, 'oops', status);
    });

    it('rejects when the network fails', async () => {
      const action = api.syncFromIntervals();
      action.catch(() => undefined);
      const request = await vi.waitFor(() => backend.expectOne((req) => req.url === SYNC));

      request.error(new ProgressEvent('error'));

      await expect(action).rejects.toThrow();
    });
  });
});
