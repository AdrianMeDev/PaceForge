import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from '../api/api-providers';
import { JobsApi } from './jobs-api';
import { JobRun, JobSettings } from './jobs-models';

const SETTINGS_URL = '/api/jobs/settings/';
const RUNS_URL = '/api/jobs/runs/';

const SETTINGS: JobSettings = { sync: true, week_review: true, week_draft: false };

const RUN: JobRun = {
  id: '01a1d196-94b6-7299-80f5-5e016f23dd2b',
  job: 'sync',
  week_start: null,
  started_at: '2026-11-12T21:07:49.046419Z',
  finished_at: '2026-11-12T21:07:50.046419Z',
  outcome: 'done',
  code: '',
  counts: { new_activities: 3 },
};

const MARK: JobRun = {
  id: 'other',
  job: 'week_review',
  week_start: '2026-11-09',
  started_at: '2026-11-15T18:00:00Z',
  finished_at: '2026-11-15T18:00:05Z',
  outcome: 'skipped',
  code: 'already_planned',
  counts: {},
};

const REFUSED = { detail: 'Authentication credentials were not provided.' };

describe('JobsApi', () => {
  let api: JobsApi;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    api = TestBed.inject(JobsApi);
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

  describe('getSettings', () => {
    it('returns the three flags as the server reports them', async () => {
      const { result } = await run(api.getSettings(), 'GET', SETTINGS_URL, SETTINGS, 200);

      expect(result).toEqual({ kind: 'ok', settings: SETTINGS });
    });

    it('treats a missing or refused session as forbidden', async () => {
      const { result } = await run(api.getSettings(), 'GET', SETTINGS_URL, REFUSED, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on answer of the wrong shape', async () => {
      await expect(
        run(
          api.getSettings(),
          'GET',
          SETTINGS_URL,
          { sync: 'yes', week_review: true, week_draft: true },
          200,
        ),
      ).rejects.toBeDefined();
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.getSettings(), 'GET', SETTINGS_URL, 'boom', 500)).rejects.toBeDefined();
    });
  });

  describe('saveSettings', () => {
    it('patches only the given flags and returns the new state', async () => {
      const { request, result } = await run(
        api.saveSettings({ week_draft: false }),
        'PATCH',
        SETTINGS_URL,
        SETTINGS,
        200,
      );

      expect(request.request.body).toEqual({ week_draft: false });
      expect(result).toEqual({ kind: 'ok', settings: SETTINGS });
    });

    it('can send a single flag while the others stay untouched', async () => {
      const { request } = await run(
        api.saveSettings({ sync: false }),
        'PATCH',
        SETTINGS_URL,
        {
          sync: false,
          week_review: true,
          week_draft: true,
        },
        200,
      );

      expect(request.request.body).toEqual({ sync: false });
    });

    it('treats a missing or refused session as forbidden', async () => {
      const { result } = await run(
        api.saveSettings({ sync: false }),
        'PATCH',
        SETTINGS_URL,
        REFUSED,
        401,
      );

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it('rejects on unexpected server errors', async () => {
      await expect(
        run(api.saveSettings({ sync: false }), 'PATCH', SETTINGS_URL, 'boom', 500),
      ).rejects.toBeDefined();
    });
  });

  describe('listRuns', () => {
    it('returns the runs in the order the server lists them', async () => {
      const { result } = await run(api.listRuns(), 'GET', RUNS_URL, [MARK, RUN], 200);

      expect(result).toEqual({ kind: 'ok', runs: [MARK, RUN] });
    });

    it('returns an empty list', async () => {
      const { result } = await run(api.listRuns(), 'GET', RUNS_URL, [], 200);

      expect(result).toEqual({ kind: 'ok', runs: [] });
    });

    it('treats a missing or refused session as forbidden', async () => {
      const { result } = await run(api.listRuns(), 'GET', RUNS_URL, REFUSED, 403);

      expect(result).toEqual({ kind: 'forbidden' });
    });

    it.each([
      ['a run with an unknown job', { ...RUN, job: 'other' }],
      ['a run with an unknown outcome', { ...RUN, outcome: 'nope' }],
      ['a run with an unknown code', { ...RUN, code: 'something_else' }],
      ['a run with non-numeric counts', { ...RUN, counts: { new_activities: 'three' } }],
      ['a run with a bad week', { ...MARK, week_start: 'not-a-date' }],
    ])('rejects %s as an answer of the wrong shape', async (_label, entry) => {
      await expect(run(api.listRuns(), 'GET', RUNS_URL, [entry], 200)).rejects.toBeDefined();
    });

    it('rejects on unexpected server errors', async () => {
      await expect(run(api.listRuns(), 'GET', RUNS_URL, 'boom', 500)).rejects.toBeDefined();
    });
  });
});
