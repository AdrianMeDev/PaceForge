import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  GetSettingsResult,
  JobCode,
  JobName,
  JobOutcome,
  JobRun,
  JobSettings,
  ListRunsResult,
  SaveSettingsResult,
  SettingsChanges,
} from './jobs-models';

const SETTINGS_URL = `${API_BASE}/jobs/settings/`;
const RUNS_URL = `${API_BASE}/jobs/runs/`;
const HANDLED_ERRORS = [400, 401, 403];

const JOB_NAMES: readonly string[] = ['sync', 'week_review', 'week_draft'];
const OUTCOMES: readonly string[] = ['done', 'skipped', 'failed'];
const CODES: readonly string[] = [
  '',
  'not_connected',
  'invalid_key',
  'intervals_unavailable',
  'no_coach',
  'provider_error',
  'plan_not_usable',
  'comment_not_usable',
  'no_time',
  'nothing_to_review',
  'already_planned',
  'unexpected',
];
const DATE = /^\d{4}-\d{2}-\d{2}$/;

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The jobs the signed-in user lets run every day or on Sunday, and the log of what they did. A
 * refused session is a value; anything unexpected (network, other server errors, an answer of the
 * wrong shape) rejects. Only the known fields are taken over and every one is checked, so that a
 * run can never carry free text from the coach or from Intervals.icu.
 */
@Injectable({ providedIn: 'root' })
export class JobsApi {
  private readonly http = inject(HttpClient);

  async getSettings(): Promise<GetSettingsResult> {
    const reply = await this.send(this.http.get(SETTINGS_URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', settings: toSettings(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async saveSettings(changes: SettingsChanges): Promise<SaveSettingsResult> {
    const reply = await this.send(this.http.patch(SETTINGS_URL, changes, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', settings: toSettings(reply.body, reply) };
      case 400:
        // Only well-formed changes are sent; a refusal here means the form and the server disagree.
        throw unexpected(reply);
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  async listRuns(): Promise<ListRunsResult> {
    const reply = await this.send(this.http.get(RUNS_URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', runs: toRuns(reply.body, reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  private async send(request: Observable<HttpResponse<unknown>>): Promise<Reply> {
    try {
      const response = await firstValueFrom(request);
      return { status: response.status, body: response.body };
    } catch (error) {
      if (error instanceof HttpErrorResponse && HANDLED_ERRORS.includes(error.status)) {
        return { status: error.status, body: error.error };
      }
      throw error;
    }
  }
}

function toSettings(body: unknown, reply: Reply): JobSettings {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    throw unexpected(reply);
  }
  const item = body as Record<string, unknown>;
  return {
    sync: flag(item['sync'], reply),
    week_review: flag(item['week_review'], reply),
    week_draft: flag(item['week_draft'], reply),
  };
}

function toRuns(body: unknown, reply: Reply): JobRun[] {
  if (!Array.isArray(body)) {
    throw unexpected(reply);
  }
  return body.map((entry) => toRun(entry, reply));
}

function toRun(body: unknown, reply: Reply): JobRun {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    throw unexpected(reply);
  }
  const item = body as Record<string, unknown>;
  const weekStart = item['week_start'];
  const counts = item['counts'];
  if (
    typeof item['id'] !== 'string' ||
    item['id'] === '' ||
    !isJob(item['job']) ||
    (weekStart !== null && (typeof weekStart !== 'string' || !DATE.test(weekStart))) ||
    typeof item['started_at'] !== 'string' ||
    typeof item['finished_at'] !== 'string' ||
    !isOutcome(item['outcome']) ||
    !isCode(item['code']) ||
    !isCounts(counts)
  ) {
    throw unexpected(reply);
  }
  return {
    id: item['id'],
    job: item['job'],
    week_start: weekStart === null ? null : (weekStart as string),
    started_at: item['started_at'] as string,
    finished_at: item['finished_at'] as string,
    outcome: item['outcome'],
    code: item['code'],
    counts: counts as Record<string, number>,
  };
}

function flag(value: unknown, reply: Reply): boolean {
  if (typeof value !== 'boolean') {
    throw unexpected(reply);
  }
  return value;
}

function isJob(value: unknown): value is JobName {
  return typeof value === 'string' && JOB_NAMES.includes(value);
}

function isOutcome(value: unknown): value is JobOutcome {
  return typeof value === 'string' && OUTCOMES.includes(value);
}

function isCode(value: unknown): value is JobCode {
  return typeof value === 'string' && CODES.includes(value);
}

/** Only small numbers, keyed by a short word, nothing else can enter the page. */
function isCounts(value: unknown): value is Record<string, number> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  return Object.entries(value).every(
    ([key, entry]) =>
      key !== '' && typeof entry === 'number' && Number.isFinite(entry) && entry >= 0,
  );
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
