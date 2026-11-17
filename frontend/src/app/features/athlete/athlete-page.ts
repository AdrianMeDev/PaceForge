import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AthleteApi } from '../../core/athlete/athlete-api';
import { CoachApi } from '../../core/coach/coach-api';
import {
  AthleteProfile,
  Metric,
  MetricOf,
  SportGroup,
  Threshold,
  ZoneSet,
} from '../../core/athlete/athlete-models';
import {
  METRIC_LABELS,
  SOURCE_LABELS,
  describeZone,
  formatValue,
  inputText,
  parseThreshold,
} from './athlete-format';
import { BestTimesPanel } from './best-times-panel';
import { AppearancePanel } from './appearance-panel';
import { BodyDataPanel } from './body-data-panel';
import { UNKNOWN_PROVIDER, providerLine } from '../availability/provider-line';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** A threshold that exists for a sport: cycling has power, running has pace; both have heart rates. */
type Row = { sport: 'ride'; metric: MetricOf<'ride'> } | { sport: 'run'; metric: MetricOf<'run'> };

interface RowView {
  /** `ride/ftp`, as the server addresses it. */
  key: string;
  /** `ride-ftp`, for ids in the page. */
  id: string;
  row: Row;
  label: string;
  /** The label with the sport, for assistive technology: several rows share a label. */
  name: string;
  threshold: Threshold;
  /** The user has typed in a value, so "Use automatic value" makes sense. */
  hasManual: boolean;
  /** The values that do not count, e.g. "Intervals.icu 262 W". */
  others: string[];
}

interface ZoneView {
  title: string;
  set: ZoneSet | null;
  /** What to do to get zones, shown when there are none. */
  hint: string;
}

interface SectionView {
  sport: SportGroup;
  title: string;
  rows: RowView[];
  zones: ZoneView[];
}

const FALLBACK = 'Something went wrong. Please try again.';
const RATE_LIMIT = 'Too many attempts. Please wait a minute and try again.';
const SYNC_FAILED = 'The thresholds could not be read from Intervals.icu. Please try again.';
const NOT_CONNECTED = 'There is no Intervals.icu connection any more.';
/** The profile page reads from Intervals.icu on its own when the last read is older than this. */
const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

const BASIS_TEXT: Record<Metric, string> = {
  ftp: 'Based on your FTP.',
  lthr: 'Based on your lactate threshold heart rate.',
  max_hr: 'Based on your maximum heart rate.',
  threshold_pace: 'Based on your threshold pace.',
};

const RIDE_ROWS: Row[] = [
  { sport: 'ride', metric: 'ftp' },
  { sport: 'ride', metric: 'lthr' },
  { sport: 'ride', metric: 'max_hr' },
];
const RUN_ROWS: Row[] = [
  { sport: 'run', metric: 'threshold_pace' },
  { sport: 'run', metric: 'lthr' },
  { sport: 'run', metric: 'max_hr' },
];

/**
 * The athlete's time zone, thresholds and training zones. Every threshold shows where its value
 * comes from; a value the user types in always counts, until they switch back to automatic. The
 * thresholds are read from Intervals.icu when the page opens and the last read is stale.
 */
@Component({
  selector: 'app-athlete-page',
  imports: [RouterLink, DatePipe, AppearancePanel, BestTimesPanel, BodyDataPanel],
  templateUrl: './athlete-page.html',
  styleUrls: ['../auth/auth-form.css', './athlete-page.css'],
})
export class AthletePage implements OnInit {
  private readonly api = inject(AthleteApi);
  private readonly coach = inject(CoachApi);

  protected readonly view = signal<View>('loading');
  protected readonly profile = signal<AthleteProfile | null>(null);
  /** One thing at a time: saving, switching to automatic, reading from Intervals.icu. */
  protected readonly busy = signal(false);
  protected readonly syncing = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);

  /** Where what the user lets go to the AI coach goes, in a few words. */
  protected readonly provider = signal(UNKNOWN_PROVIDER);

  protected readonly timezoneDraft = signal('');
  protected readonly timezoneError = signal<string | null>(null);
  protected readonly timeZones = knownTimeZones();

  /** The key of the threshold being edited (`ride/ftp`), if any. */
  protected readonly editing = signal<string | null>(null);
  protected readonly draft = signal('');
  protected readonly rowError = signal<string | null>(null);

  /** When the thresholds were last read; `null` if never, or if the server's text is no date. */
  protected readonly lastRead = computed<Date | null>(() => {
    const text = this.profile()?.intervals.synced_at;
    const time = text ? Date.parse(text) : Number.NaN;
    return Number.isNaN(time) ? null : new Date(time);
  });

  protected readonly sections = computed<SectionView[]>(() => {
    const profile = this.profile();
    return profile ? sectionsOf(profile) : [];
  });

  protected readonly sourceLabel = SOURCE_LABELS;
  protected readonly zoneRange = describeZone;
  protected readonly basisText = BASIS_TEXT;
  protected readonly valueText = (row: Row, value: number): string =>
    formatValue(row.metric, value);

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    let loaded: AthleteProfile;
    try {
      const result = await this.api.get();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      loaded = result.profile;
    } catch {
      this.view.set('unreachable');
      return;
    }
    this.take(loaded);
    this.view.set('ready');
    void this.loadProvider();
    if (isStale(loaded)) {
      await this.readFromIntervals(true);
    }
  }

  /** The provider is only named in a hint: if it cannot be read, the hint says so in general. */
  private async loadProvider(): Promise<void> {
    try {
      const result = await this.coach.get();
      this.provider.set(providerLine(result.kind === 'ok' ? result.state : null));
    } catch {
      this.provider.set(UNKNOWN_PROVIDER);
    }
  }

  // --- body and training data

  protected onProfileChanged(profile: AthleteProfile): void {
    this.profile.set(profile);
  }

  protected endSession(): void {
    this.view.set('signed_out');
  }

  // --- time zone

  protected onTimezone(event: Event): void {
    this.timezoneDraft.set((event.target as HTMLInputElement).value);
  }

  protected useDeviceTimezone(): void {
    this.timezoneDraft.set(deviceTimezone());
    this.timezoneError.set(null);
  }

  protected async saveTimezone(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.timezoneError.set(null);
    this.busy.set(true);
    try {
      const result = await this.api.setTimezone(this.timezoneDraft().trim());
      switch (result.kind) {
        case 'ok':
          this.take(result.profile);
          this.notice.set(
            result.profile.timezone ? 'The time zone was saved.' : 'The time zone was removed.',
          );
          break;
        case 'invalid':
          this.timezoneError.set(result.errors.join(' '));
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  // --- thresholds

  protected startEdit(item: RowView): void {
    this.clearMessages();
    this.editing.set(item.key);
    const effective = item.threshold.effective;
    this.draft.set(effective ? inputText(item.row.metric, effective.value) : '');
    this.rowError.set(null);
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.rowError.set(null);
  }

  protected onDraft(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
  }

  protected async save(item: RowView): Promise<void> {
    if (this.busy()) {
      return;
    }
    const parsed = parseThreshold(item.row.metric, this.draft());
    if (!parsed.ok) {
      this.rowError.set(parsed.error);
      return;
    }
    this.clearMessages();
    this.rowError.set(null);
    this.busy.set(true);
    try {
      const { row } = item;
      const result =
        row.sport === 'ride'
          ? await this.api.setThreshold('ride', row.metric, parsed.value)
          : await this.api.setThreshold('run', row.metric, parsed.value);
      switch (result.kind) {
        case 'ok':
          this.take(result.profile);
          this.editing.set(null);
          this.notice.set(`${item.label} was saved.`);
          break;
        case 'invalid':
          this.rowError.set(result.errors.join(' '));
          break;
        case 'not_found':
          this.errors.set([`${item.label} does not exist for this sport.`]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async useAutomatic(item: RowView): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const { row } = item;
      const result =
        row.sport === 'ride'
          ? await this.api.clearThreshold('ride', row.metric)
          : await this.api.clearThreshold('run', row.metric);
      switch (result.kind) {
        case 'ok':
          // A field that is open (another row's, since this row's offers no such button) stays.
          this.take(result.profile);
          this.notice.set(`${item.label} is automatic again.`);
          break;
        case 'not_found':
          this.errors.set([`${item.label} does not exist for this sport.`]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  // --- Intervals.icu

  protected syncNow(): Promise<void> {
    return this.readFromIntervals(false);
  }

  private async readFromIntervals(automatic: boolean): Promise<void> {
    if (this.busy()) {
      return;
    }
    if (!automatic) {
      this.clearMessages();
    }
    this.busy.set(true);
    this.syncing.set(true);
    try {
      const result = await this.api.syncFromIntervals();
      switch (result.kind) {
        case 'ok':
          this.take(result.profile);
          if (!automatic) {
            this.notice.set('The thresholds were updated from Intervals.icu.');
          }
          break;
        case 'not_connected':
          this.errors.set([NOT_CONNECTED]);
          break;
        case 'key_refused':
        case 'unavailable':
          this.errors.set([result.message]);
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMIT]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([SYNC_FAILED]);
    } finally {
      this.syncing.set(false);
      this.busy.set(false);
    }
  }

  /** Takes over a profile from the server; the time zone field follows it. */
  private take(profile: AthleteProfile): void {
    this.profile.set(profile);
    this.timezoneDraft.set(profile.timezone);
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}

function sectionsOf(profile: AthleteProfile): SectionView[] {
  const { ride, run } = profile.sports;
  return [
    {
      sport: 'ride',
      title: 'Cycling',
      rows: RIDE_ROWS.map((row) => rowView(row, 'Cycling', thresholdOf(profile, row))),
      zones: [
        {
          title: 'Power zones',
          set: ride.zones.power,
          hint: 'Set your FTP to see power zones.',
        },
        { title: 'Heart rate zones', set: ride.zones.heart_rate, hint: HEART_RATE_HINT },
      ],
    },
    {
      sport: 'run',
      title: 'Running',
      rows: RUN_ROWS.map((row) => rowView(row, 'Running', thresholdOf(profile, row))),
      zones: [
        {
          title: 'Pace zones',
          set: run.zones.pace,
          hint: 'Set your threshold pace to see pace zones.',
        },
        { title: 'Heart rate zones', set: run.zones.heart_rate, hint: HEART_RATE_HINT },
      ],
    },
  ];
}

const HEART_RATE_HINT = 'Set a lactate threshold or a maximum heart rate to see heart rate zones.';

function thresholdOf(profile: AthleteProfile, row: Row): Threshold {
  return row.sport === 'ride'
    ? profile.sports.ride.thresholds[row.metric]
    : profile.sports.run.thresholds[row.metric];
}

function rowView(row: Row, sportTitle: string, threshold: Threshold): RowView {
  return {
    key: `${row.sport}/${row.metric}`,
    id: `${row.sport}-${row.metric}`,
    row,
    label: METRIC_LABELS[row.metric],
    name: `${METRIC_LABELS[row.metric]} (${sportTitle})`,
    threshold,
    hasManual: threshold.candidates.some((candidate) => candidate.source === 'manual'),
    others: threshold.candidates
      .filter((candidate) => candidate !== threshold.effective)
      .map(
        (candidate) =>
          `${SOURCE_LABELS[candidate.source]} ${formatValue(row.metric, candidate.value)}`,
      ),
  };
}

function isStale(profile: AthleteProfile): boolean {
  if (!profile.intervals.connected) {
    return false;
  }
  const syncedAt = profile.intervals.synced_at;
  if (syncedAt === null) {
    return true;
  }
  const time = Date.parse(syncedAt);
  return Number.isNaN(time) || Date.now() - time > STALE_AFTER_MS;
}

/** The time zone of this device, or an empty text if the browser does not say. */
function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? '';
  } catch {
    return '';
  }
}

/** The time zones this browser knows, for the suggestions of the field. */
function knownTimeZones(): string[] {
  try {
    return Intl.supportedValuesOf('timeZone');
  } catch {
    return [];
  }
}
