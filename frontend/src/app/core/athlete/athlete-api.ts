import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  AthleteProfile,
  BestTime,
  BestTimeDistance,
  BestTimeInput,
  BodyAndTraining,
  BodyChanges,
  ClearBestTimeResult,
  ClearThresholdResult,
  CountingVdot,
  Equipment,
  GetAthleteResult,
  Metric,
  MetricOf,
  RideProfile,
  RunProfile,
  SaveBodyResult,
  SetBestTimeResult,
  SetThresholdResult,
  SetTimezoneResult,
  Sex,
  SportGroup,
  StrengthExperience,
  SyncResult,
  Threshold,
  ThresholdSource,
  ThresholdValue,
  TrainingSport,
  TrainingYears,
  Zone,
  ZoneSet,
  ZoneUnit,
} from './athlete-models';

const URL = `${API_BASE}/athlete/`;
const SYNC_URL = `${URL}sync/`;
const INVALID_FALLBACK = 'The input was not accepted.';
const KEY_REFUSED_FALLBACK =
  'Intervals.icu did not accept the stored API key. Enter it again on the Connections page.';
const UNAVAILABLE_FALLBACK = 'Intervals.icu cannot be reached right now. Please try again later.';
const HANDLED_ERRORS = [400, 401, 403, 404, 409, 429, 502, 503];
const SOURCES: readonly string[] = ['manual', 'best_time', 'intervals', 'estimated'];
const METRICS: readonly string[] = ['ftp', 'lthr', 'max_hr', 'threshold_pace'];
const UNITS: readonly string[] = ['W', 'bpm', 's/km'];
const DISTANCES: readonly BestTimeDistance[] = ['5k', '10k', 'half_marathon', 'marathon'];
const SEXES: readonly string[] = ['female', 'male', 'other'];
const EXPERIENCES: readonly string[] = ['beginner', 'advanced'];
const EQUIPMENT: readonly string[] = ['gym', 'home', 'dumbbells'];
const TRAINING_SPORTS: readonly TrainingSport[] = ['running', 'cycling', 'swimming', 'strength'];

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The signed-in user's athlete profile. Problems that people can act on are values; anything
 * unexpected (network, other server errors, an answer of the wrong shape) rejects. Every
 * successful call answers with the whole profile, so the page can show new values and zones
 * after one call.
 */
@Injectable({ providedIn: 'root' })
export class AthleteApi {
  private readonly http = inject(HttpClient);

  async get(): Promise<GetAthleteResult> {
    const reply = await this.send(this.http.get(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** An empty name removes the time zone. */
  async setTimezone(timezone: string): Promise<SetTimezoneResult> {
    const reply = await this.send(this.http.patch(URL, { timezone }, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 400:
        return { kind: 'invalid', errors: messagesOf(reply.body) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Changes the body and training data given; `null` clears a field, others stay as they are. */
  async saveBody(changes: BodyChanges): Promise<SaveBodyResult> {
    const reply = await this.send(this.http.patch(URL, changes, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 400:
        return { kind: 'invalid', errors: messagesOf(reply.body), fields: fieldsOf(reply.body) };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Sets the best time over a distance; a new one replaces the old one. */
  async setBestTime(distance: BestTimeDistance, input: BestTimeInput): Promise<SetBestTimeResult> {
    const reply = await this.send(
      this.http.put(bestTimeUrl(distance), input, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 400:
        return { kind: 'invalid', errors: messagesOf(reply.body), fields: fieldsOf(reply.body) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Removes the best time over a distance. Removing one that is not there is fine. */
  async clearBestTime(distance: BestTimeDistance): Promise<ClearBestTimeResult> {
    const reply = await this.send(this.http.delete(bestTimeUrl(distance), { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Stores the value the user typed in; it counts before every other source. */
  async setThreshold<S extends SportGroup>(
    sport: S,
    metric: MetricOf<S>,
    value: number,
  ): Promise<SetThresholdResult> {
    const reply = await this.send(
      this.http.put(thresholdUrl(sport, metric), { value }, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 400:
        return { kind: 'invalid', errors: messagesOf(reply.body) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Back to automatic. Removing a value that is not there is fine. */
  async clearThreshold<S extends SportGroup>(
    sport: S,
    metric: MetricOf<S>,
  ): Promise<ClearThresholdResult> {
    const reply = await this.send(
      this.http.delete(thresholdUrl(sport, metric), { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 404:
        return { kind: 'not_found' };
      case 401:
      case 403:
        return { kind: 'forbidden' };
      default:
        throw unexpected(reply);
    }
  }

  /** Reads the thresholds from the user's Intervals.icu sport settings. */
  async syncFromIntervals(): Promise<SyncResult> {
    const reply = await this.send(this.http.post(SYNC_URL, {}, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', profile: toProfile(reply) };
      case 404:
        return { kind: 'not_connected' };
      case 409:
        return { kind: 'key_refused', message: detailOf(reply.body) ?? KEY_REFUSED_FALLBACK };
      case 429:
        return { kind: 'rate_limited' };
      case 502:
      case 503:
        return {
          kind: 'unavailable',
          message: detailOf(reply.body) ?? UNAVAILABLE_FALLBACK,
        };
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

function bestTimeUrl(distance: BestTimeDistance): string {
  return `${URL}best-times/${encodeURIComponent(distance)}/`;
}

function thresholdUrl(sport: string, metric: string): string {
  return `${URL}thresholds/${encodeURIComponent(sport)}/${encodeURIComponent(metric)}/`;
}

/** Only the known fields are taken over, whatever else an answer might carry. */
function toProfile(reply: Reply): AthleteProfile {
  const body = asObject(reply.body, reply);
  const intervals = asObject(body['intervals'], reply);
  const sports = asObject(body['sports'], reply);
  const synced = intervals['synced_at'] ?? null;
  if (
    typeof body['timezone'] !== 'string' ||
    typeof intervals['connected'] !== 'boolean' ||
    (synced !== null && typeof synced !== 'string')
  ) {
    throw unexpected(reply);
  }
  return {
    ...toBody(body, reply),
    ...toRaces(body, reply),
    timezone: body['timezone'],
    intervals: { connected: intervals['connected'], synced_at: synced },
    sports: {
      ride: toRide(sports['ride'], reply),
      run: toRun(sports['run'], reply),
    },
  };
}

/** The best times of every distance and the VDOT that counts; a missing key is the wrong shape. */
function toRaces(
  body: Record<string, unknown>,
  reply: Reply,
): { best_times: Record<BestTimeDistance, BestTime | null>; vdot: CountingVdot | null } {
  const times = asObject(body['best_times'], reply);
  const counting = body['vdot'];
  return {
    best_times: Object.fromEntries(
      DISTANCES.map((distance) => [distance, toBestTime(times[distance], reply)]),
    ) as Record<BestTimeDistance, BestTime | null>,
    vdot: counting === null ? null : toCountingVdot(counting, reply),
  };
}

function toBestTime(raw: unknown, reply: Reply): BestTime | null {
  if (raw === null) {
    return null;
  }
  const item = asObject(raw, reply);
  if (
    typeof item['seconds'] !== 'number' ||
    !Number.isInteger(item['seconds']) ||
    item['seconds'] < 1 ||
    !isDay(item['date']) ||
    typeof item['vdot'] !== 'number' ||
    !Number.isFinite(item['vdot']) ||
    typeof item['recent'] !== 'boolean' ||
    typeof item['counts'] !== 'boolean'
  ) {
    throw unexpected(reply);
  }
  return {
    seconds: item['seconds'],
    date: item['date'],
    vdot: item['vdot'],
    recent: item['recent'],
    counts: item['counts'],
  };
}

function toCountingVdot(raw: unknown, reply: Reply): CountingVdot {
  const item = asObject(raw, reply);
  if (
    typeof item['value'] !== 'number' ||
    !Number.isFinite(item['value']) ||
    !isOneOf<BestTimeDistance>(item['distance'], DISTANCES) ||
    !isDay(item['date'])
  ) {
    throw unexpected(reply);
  }
  return { value: item['value'], distance: item['distance'], date: item['date'] };
}

function isDay(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

/** The body and training data; every field has to be there, `null` where nothing was said. */
function toBody(body: Record<string, unknown>, reply: Reply): BodyAndTraining {
  const years = asObject(body['training_years'], reply);
  const equipment = body['strength_equipment'];
  const sex = body['sex'];
  const experience = body['strength_experience'];
  if (
    (sex !== null && !isOneOf<Sex>(sex, SEXES)) ||
    (experience !== null && !isOneOf<StrengthExperience>(experience, EXPERIENCES)) ||
    !Array.isArray(equipment) ||
    !equipment.every((item) => isOneOf<Equipment>(item, EQUIPMENT)) ||
    new Set(equipment).size !== equipment.length
  ) {
    throw unexpected(reply);
  }
  return {
    birth_year: wholeNumberOrNull(body['birth_year'], reply),
    sex,
    weight_kg: numberOrNullStrict(body['weight_kg'], reply),
    resting_hr: wholeNumberOrNull(body['resting_hr'], reply),
    training_years: Object.fromEntries(
      TRAINING_SPORTS.map((sport) => [sport, wholeNumberOrNull(years[sport], reply)]),
    ) as TrainingYears,
    strength_experience: experience,
    strength_equipment: [...(equipment as Equipment[])],
  };
}

function toRide(raw: unknown, reply: Reply): RideProfile {
  const sport = asObject(raw, reply);
  const thresholds = asObject(sport['thresholds'], reply);
  const zones = asObject(sport['zones'], reply);
  return {
    thresholds: {
      ftp: toThreshold(thresholds['ftp'], reply),
      lthr: toThreshold(thresholds['lthr'], reply),
      max_hr: toThreshold(thresholds['max_hr'], reply),
    },
    zones: {
      power: toZoneSet(zones['power'], reply),
      heart_rate: toZoneSet(zones['heart_rate'], reply),
    },
  };
}

function toRun(raw: unknown, reply: Reply): RunProfile {
  const sport = asObject(raw, reply);
  const thresholds = asObject(sport['thresholds'], reply);
  const zones = asObject(sport['zones'], reply);
  return {
    thresholds: {
      threshold_pace: toThreshold(thresholds['threshold_pace'], reply),
      lthr: toThreshold(thresholds['lthr'], reply),
      max_hr: toThreshold(thresholds['max_hr'], reply),
    },
    zones: {
      pace: toZoneSet(zones['pace'], reply),
      heart_rate: toZoneSet(zones['heart_rate'], reply),
    },
  };
}

function toThreshold(raw: unknown, reply: Reply): Threshold {
  const threshold = asObject(raw, reply);
  const candidates = threshold['candidates'];
  if (!Array.isArray(candidates)) {
    throw unexpected(reply);
  }
  const effective = threshold['effective'];
  return {
    effective: effective === null || effective === undefined ? null : toValue(effective, reply),
    candidates: candidates.map((candidate) => toValue(candidate, reply)),
  };
}

function toValue(raw: unknown, reply: Reply): ThresholdValue {
  const item = asObject(raw, reply);
  if (
    typeof item['value'] !== 'number' ||
    !Number.isFinite(item['value']) ||
    !isSource(item['source']) ||
    typeof item['basis'] !== 'string' ||
    typeof item['updated_at'] !== 'string'
  ) {
    throw unexpected(reply);
  }
  return {
    value: item['value'],
    source: item['source'],
    basis: item['basis'],
    updated_at: item['updated_at'],
  };
}

function toZoneSet(raw: unknown, reply: Reply): ZoneSet | null {
  if (raw === null || raw === undefined) {
    return null;
  }
  const set = asObject(raw, reply);
  if (!isMetric(set['basis']) || !Array.isArray(set['zones'])) {
    throw unexpected(reply);
  }
  return { basis: set['basis'], zones: set['zones'].map((zone) => toZone(zone, reply)) };
}

function toZone(raw: unknown, reply: Reply): Zone {
  const zone = asObject(raw, reply);
  if (
    typeof zone['number'] !== 'number' ||
    !Number.isInteger(zone['number']) ||
    typeof zone['name'] !== 'string' ||
    !isUnit(zone['unit'])
  ) {
    throw unexpected(reply);
  }
  return {
    number: zone['number'],
    name: zone['name'],
    lower: numberOrNull(zone['lower'], reply),
    upper: numberOrNull(zone['upper'], reply),
    unit: zone['unit'],
  };
}

function asObject(value: unknown, reply: Reply): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw unexpected(reply);
  }
  return value as Record<string, unknown>;
}

/** A missing limit is `null`; anything else that is not a number is an answer of the wrong shape. */
function numberOrNull(value: unknown, reply: Reply): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw unexpected(reply);
  }
  return value;
}

/** `null` or a whole number; a missing key is an answer of the wrong shape. */
function wholeNumberOrNull(value: unknown, reply: Reply): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw unexpected(reply);
  }
  return value;
}

/** `null` or a finite number; a missing key is an answer of the wrong shape. */
function numberOrNullStrict(value: unknown, reply: Reply): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw unexpected(reply);
  }
  return value;
}

function isOneOf<T extends string>(value: unknown, allowed: readonly string[]): value is T {
  return typeof value === 'string' && allowed.includes(value);
}

function isSource(value: unknown): value is ThresholdSource {
  return typeof value === 'string' && SOURCES.includes(value);
}

function isMetric(value: unknown): value is Metric {
  return typeof value === 'string' && METRICS.includes(value);
}

function isUnit(value: unknown): value is ZoneUnit {
  return typeof value === 'string' && UNITS.includes(value);
}

function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' && detail ? detail : null;
}

/** The messages of each field of a refusal; fields without a usable text are left out. */
function fieldsOf(body: unknown): Record<string, string[]> {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return {};
  }
  const fields: Record<string, string[]> = {};
  for (const [name, value] of Object.entries(body)) {
    const texts = (Array.isArray(value) ? value : [value]).filter(
      (text): text is string => typeof text === 'string',
    );
    if (texts.length) {
      fields[name] = texts;
    }
  }
  return fields;
}

/** DRF reports field errors as `{"value": ["…"]}` and other problems as `{"detail": "…"}`. */
function messagesOf(body: unknown): string[] {
  if (typeof body !== 'object' || body === null) {
    return [INVALID_FALLBACK];
  }
  const messages = Object.values(body)
    .flat()
    .filter((value): value is string => typeof value === 'string');
  return messages.length ? messages : [INVALID_FALLBACK];
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
