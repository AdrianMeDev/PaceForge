import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { SeasonApi } from './season-api';
import { Season } from './season-models';

const URL = '/api/season/';

const RACE = {
  date: '2027-02-28',
  priority: 'main',
  discipline: 'running',
  distance_m: 42195,
  title: 'Berlin Marathon',
};
const SEASON = {
  rolling: false,
  truncated: false,
  main_race: RACE,
  peak_minutes: 300,
  weeks: [
    {
      week_start: '2026-11-16',
      phase: 'base',
      recovery: false,
      target_minutes: 240,
      capacity_minutes: 300,
      races: [],
    },
    {
      week_start: '2026-11-23',
      phase: 'base',
      recovery: true,
      target_minutes: 156,
      capacity_minutes: 300,
      races: [{ ...RACE, priority: 'preparation', discipline: null, distance_m: null }],
    },
    {
      week_start: '2027-02-22',
      phase: 'taper',
      recovery: false,
      target_minutes: 135,
      capacity_minutes: 300,
      races: [RACE],
    },
  ],
};
const ROLLING = { ...SEASON, rolling: true, main_race: null, weeks: [] };
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

describe('SeasonApi', () => {
  let api: SeasonApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(SeasonApi);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function run<T>(
    action: Promise<T>,
    reply: string | object | null,
    status: number,
  ): Promise<{ result: T; request: TestRequest }> {
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    return { result: await action, request };
  }

  async function runFailing(
    action: Promise<unknown>,
    reply: string | object | null,
    status: number,
  ): Promise<void> {
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.flush(reply, { status, statusText: `HTTP ${status}` });
    await expect(action).rejects.toThrow();
  }

  it('reads the weeks, the races and the peak', async () => {
    const { result, request } = await run(api.get(), SEASON, 200);

    expect(request.request.body).toBeNull();
    expect(result).toEqual({ kind: 'ok', season: SEASON as Season });
  });

  it('reads a rolling skeleton without a main race', async () => {
    const { result } = await run(api.get(), ROLLING, 200);

    expect(result).toMatchObject({ kind: 'ok', season: { rolling: true, main_race: null } });
  });

  it('takes over only the known fields', async () => {
    const crowded = altered(
      SEASON,
      [['owner'], 'x'],
      [['weeks', 0, 'note'], 'secret'],
      [['main_race', 'internal'], 1],
    );

    const { result } = await run(api.get(), crowded as object, 200);

    expect(result).toEqual({ kind: 'ok', season: SEASON as Season });
  });

  it.each([401, 403])('says when the session is gone (%i)', async (status) => {
    const { result } = await run(api.get(), NO_SESSION, status);

    expect(result).toEqual({ kind: 'forbidden' });
  });

  it.each([
    ['no body', null],
    ['a list as body', []],
    ['a text as body', 'season'],
    ['no rolling flag', altered(SEASON, [['rolling'], REMOVE])],
    ['a text as rolling flag', altered(SEASON, [['rolling'], 'false'])],
    ['no truncated flag', altered(SEASON, [['truncated'], REMOVE])],
    ['a rolling skeleton with a main race', altered(SEASON, [['rolling'], true])],
    ['no main race without rolling', altered(SEASON, [['main_race'], null])],
    ['a fractional peak', altered(SEASON, [['peak_minutes'], 1.5])],
    ['a negative peak', altered(SEASON, [['peak_minutes'], -1])],
    ['no weeks', altered(SEASON, [['weeks'], REMOVE])],
    ['an object as weeks', altered(SEASON, [['weeks'], {}])],
    ['more than 52 weeks', altered(SEASON, [['weeks'], Array(53).fill(SEASON.weeks[0])])],
    ['a text as week', altered(SEASON, [['weeks'], ['week']])],
    ['a week without a start', altered(SEASON, [['weeks', 0, 'week_start'], REMOVE])],
    ['a start that is no date', altered(SEASON, [['weeks', 0, 'week_start'], 'monday'])],
    ['an unknown phase', altered(SEASON, [['weeks', 0, 'phase'], 'peak'])],
    ['no recovery flag', altered(SEASON, [['weeks', 0, 'recovery'], REMOVE])],
    ['a fractional target', altered(SEASON, [['weeks', 0, 'target_minutes'], 10.5])],
    ['a negative capacity', altered(SEASON, [['weeks', 0, 'capacity_minutes'], -5])],
    ['a target above the capacity', altered(SEASON, [['weeks', 0, 'target_minutes'], 301])],
    ['no races', altered(SEASON, [['weeks', 0, 'races'], REMOVE])],
    ['a text as a race', altered(SEASON, [['weeks', 2, 'races'], ['Berlin']])],
    ['a race without a date', altered(SEASON, [['main_race', 'date'], REMOVE])],
    ['a race date with a time', altered(SEASON, [['main_race', 'date'], '2027-02-28T10:00:00Z'])],
    ['an unknown priority', altered(SEASON, [['main_race', 'priority'], 'urgent'])],
    ['an unknown discipline', altered(SEASON, [['main_race', 'discipline'], 'rowing'])],
    ['no discipline', altered(SEASON, [['main_race', 'discipline'], REMOVE])],
    ['a text as distance', altered(SEASON, [['main_race', 'distance_m'], '42195'])],
    ['a zero distance', altered(SEASON, [['main_race', 'distance_m'], 0])],
    ['no distance', altered(SEASON, [['main_race', 'distance_m'], REMOVE])],
    ['no title', altered(SEASON, [['main_race', 'title'], REMOVE])],
    ['a number as title', altered(SEASON, [['main_race', 'title'], 5])],
  ])('rejects an answer with %s', async (_name, bad) => {
    await runFailing(api.get(), bad as object | null, 200);
  });

  it.each([404, 500])('rejects the unexpected status %i', async (status) => {
    await runFailing(api.get(), 'oops', status);
  });

  it('rejects when the network fails', async () => {
    const action = api.get();
    action.catch(() => undefined);
    const request = await vi.waitFor(() =>
      backend.expectOne((req) => req.method === 'GET' && req.url === URL),
    );
    request.error(new ProgressEvent('error'));

    await expect(action).rejects.toThrow();
  });
});
