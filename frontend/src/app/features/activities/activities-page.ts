import { DOCUMENT, DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { ActivitiesApi } from '../../core/activities/activities-api';
import {
  Activity,
  ActivityPage,
  ImportActivityResult,
} from '../../core/activities/activities-models';
import { IntervalsConnectionApi } from '../../core/integrations/intervals-api';
import { IntervalsConnection } from '../../core/integrations/intervals-models';
import {
  SPORT_CHOICES,
  formatDistance,
  formatDuration,
  formatHeartRate,
  formatLoad,
  formatRpe,
  sourceLabel,
  sportLabel,
} from './activity-format';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { Icon } from '../../shared/icon';
import { PageHeader } from '../../shared/page-header';
import { ManualActivityForm } from './manual-activity-form';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** What happened to one file. `failed`: the request itself did not work (network, server error). */
type Outcome = Exclude<ImportActivityResult, { kind: 'forbidden' }> | { kind: 'failed' };

interface FileResult {
  name: string;
  outcome: Outcome;
}

const PAGE_SIZE = 20;
const FALLBACK = 'Something went wrong. Please try again.';
const REFRESH_FAILED = 'The list could not be refreshed. Please try again.';

/**
 * Where users bring FIT, TCX and GPX files (also gzip-compressed) in and see what was imported. The server decides by the
 * content of a file, never by its name; files are sent one after the other so that each gets its
 * own result and one failure does not stop the others.
 */
@Component({
  selector: 'app-activities-page',
  imports: [RouterLink, DatePipe, ConfirmDialog, Icon, PageHeader, ManualActivityForm],
  templateUrl: './activities-page.html',
  styleUrl: './activities-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ActivitiesPage implements OnInit {
  private readonly api = inject(ActivitiesApi);
  private readonly intervals = inject(IntervalsConnectionApi);
  private readonly document = inject(DOCUMENT);

  protected readonly view = signal<View>('loading');
  protected readonly page = signal<ActivityPage>({ count: 0, results: [] });
  protected readonly offset = signal(0);
  /** An import, sync or deletion is running: nothing else may start. */
  protected readonly busy = signal(false);
  /** Undefined until the optional connection status is known; null means not connected. */
  protected readonly connection = signal<IntervalsConnection | null | undefined>(undefined);
  /** The list is being fetched again (paging, after an import or a deletion). */
  protected readonly refreshing = signal(false);
  protected readonly currentFile = signal<string | null>(null);
  protected readonly results = signal<FileResult[]>([]);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The activity the dialog asks about. */
  protected readonly confirming = signal<Activity | null>(null);
  private readonly deleteDialog = viewChild(ConfirmDialog);
  protected readonly highlighted = signal<string | null>(null);
  /** The sport the list is kept to; `null`: all of them. */
  protected readonly filter = signal<Activity['sport'] | null>(null);
  /** Files are being dragged over the drop zone. */
  protected readonly dragging = signal(false);

  /** The line under the title: how many activities there are. */
  protected readonly subtitle = computed(() => {
    const count = this.page().count;
    return this.view() !== 'ready' || count === 0
      ? ''
      : `${count} ${count === 1 ? 'activity' : 'activities'}`;
  });
  protected readonly first = computed(() => (this.page().results.length ? this.offset() + 1 : 0));
  protected readonly last = computed(() => this.offset() + this.page().results.length);
  protected readonly hasPrevious = computed(() => this.offset() > 0);
  protected readonly hasNext = computed(() => this.last() < this.page().count);
  protected readonly previousOffset = computed(() => Math.max(0, this.offset() - PAGE_SIZE));
  protected readonly nextOffset = computed(() => this.offset() + PAGE_SIZE);
  protected readonly listedIds = computed(() => this.page().results.map((a) => a.id));

  protected readonly sports = SPORT_CHOICES;
  protected readonly filterLabel = computed(
    () => SPORT_CHOICES.find((choice) => choice.value === this.filter())?.label.toLowerCase() ?? '',
  );
  protected readonly sport = sportLabel;
  protected readonly source = sourceLabel;
  protected readonly distance = formatDistance;
  protected readonly heartRate = formatHeartRate;
  protected readonly rpeText = formatRpe;
  protected readonly loadText = formatLoad;
  protected readonly duration = (activity: Activity): string =>
    formatDuration(activity.timer_seconds ?? activity.elapsed_seconds);

  ngOnInit(): Promise<void> {
    void this.loadConnection();
    return this.load();
  }

  private async loadConnection(): Promise<void> {
    try {
      const result = await this.intervals.get();
      if (result.kind !== 'forbidden') {
        this.connection.set(result.kind === 'connected' ? result.connection : null);
      }
    } catch {
      // The activity list and file imports remain usable without connection status.
    }
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    const outcome = await this.fetch(0);
    this.view.set(
      outcome === 'ok' ? 'ready' : outcome === 'signed_out' ? 'signed_out' : 'unreachable',
    );
  }

  protected async select(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = ''; // so that the same file can be chosen again
    if (files.length === 0 || this.busy()) {
      return;
    }
    await this.importAll(files);
  }

  protected async syncFromIntervals(): Promise<void> {
    if (this.busy() || this.refreshing() || this.connection()?.status !== 'connected') {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.syncFromIntervals();
      switch (result.kind) {
        case 'ok':
          this.connection.update((connection) =>
            connection
              ? { ...connection, last_sync_at: result.last_sync_at, last_sync_error: '' }
              : connection,
          );
          this.notice.set(
            `Intervals.icu sync: ${result.imported} imported; ${result.skipped_duplicates} duplicates skipped; ${result.skipped_strava} Strava activities skipped; ${result.skipped_invalid} invalid activities skipped; ${result.wellness_synced} wellness days synced.`,
          );
          if (result.imported > 0) {
            await this.refresh(0);
          }
          break;
        case 'not_connected':
          this.connection.set(null);
          this.errors.set(['Intervals.icu is no longer connected. Connect it on Connections.']);
          break;
        case 'invalid_key':
          this.connection.update((connection) =>
            connection
              ? { ...connection, status: 'invalid', last_sync_error: 'invalid_key' }
              : connection,
          );
          this.errors.set([
            'Intervals.icu did not accept the stored key. Update it on Connections.',
          ]);
          break;
        case 'rate_limited':
          this.errors.set(['Too many sync attempts. Please wait a minute and try again.']);
          break;
        case 'unavailable':
          this.errors.set([result.message]);
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

  /** Files over the zone: the browser must be told that they may be dropped, or it opens them. */
  protected dragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(!this.busy());
  }

  protected dragLeave(event: DragEvent): void {
    const zone = event.currentTarget as HTMLElement;
    if (!(event.relatedTarget instanceof Node) || !zone.contains(event.relatedTarget)) {
      this.dragging.set(false);
    }
  }

  /** Dropped files go the way chosen ones go; while something runs they are ignored. */
  protected async drop(event: DragEvent): Promise<void> {
    event.preventDefault();
    this.dragging.set(false);
    const files = Array.from(event.dataTransfer?.files ?? []);
    if (files.length === 0 || this.busy()) {
      return;
    }
    await this.importAll(files);
  }

  /** Keeps the list to one sport (or, with `null`, shows all): it starts again at the newest. */
  protected async filterBy(sport: Activity['sport'] | null): Promise<void> {
    if (this.busy() || this.refreshing()) {
      return;
    }
    this.clearMessages();
    this.filter.set(sport);
    await this.refresh(0);
  }

  /** A session was entered by hand: the list starts again at the newest activity. */
  protected async entered(): Promise<void> {
    this.clearMessages();
    await this.refresh(0);
  }

  protected signOut(): void {
    this.view.set('signed_out');
  }

  protected async goTo(offset: number): Promise<void> {
    if (this.busy() || this.refreshing()) {
      return;
    }
    this.clearMessages();
    await this.refresh(offset);
  }

  protected askDelete(activity: Activity): void {
    this.clearMessages();
    this.confirming.set(activity);
    this.deleteDialog()?.open();
  }

  /** The dialog was answered with "Delete activity". */
  protected async delete(): Promise<void> {
    const activity = this.confirming();
    if (this.busy() || activity === null) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.delete(activity.id);
      this.confirming.set(null);
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.notice.set(
        result.kind === 'deleted' ? 'The activity was deleted.' : 'The activity was already gone.',
      );
      await this.refresh(this.offset());
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected isListed(id: string): boolean {
    return this.page().results.some((activity) => activity.id === id);
  }

  /** Moves the focus to the row of an activity that is already there. */
  protected showRow(id: string): void {
    this.highlighted.set(id);
    this.document.getElementById(`activity-${id}`)?.focus();
  }

  private async importAll(files: File[]): Promise<void> {
    this.clearMessages();
    this.results.set([]);
    this.busy.set(true);
    try {
      let imported = false;
      for (const file of files) {
        this.currentFile.set(file.name);
        const outcome = await this.importOne(file);
        if (outcome.kind === 'forbidden') {
          this.view.set('signed_out');
          return;
        }
        imported ||= outcome.kind === 'imported';
        this.results.update((list) => [...list, { name: file.name, outcome }]);
      }
      if (imported) {
        await this.refresh(0);
      }
    } finally {
      this.currentFile.set(null);
      this.busy.set(false);
    }
  }

  private async importOne(file: File): Promise<Outcome | { kind: 'forbidden' }> {
    try {
      return await this.api.import(file);
    } catch {
      return { kind: 'failed' };
    }
  }

  /** Fetches the list again without leaving the page; a failure is shown above the list. */
  private async refresh(offset: number): Promise<void> {
    this.refreshing.set(true);
    try {
      const outcome = await this.fetch(offset);
      if (outcome === 'signed_out') {
        this.view.set('signed_out');
      } else if (outcome === 'failed') {
        this.errors.update((list) => [...list, REFRESH_FAILED]);
      }
    } finally {
      this.refreshing.set(false);
    }
  }

  private async fetch(offset: number): Promise<'ok' | 'failed' | 'signed_out'> {
    try {
      const sport = this.filter();
      const result =
        sport === null
          ? await this.api.list(PAGE_SIZE, offset)
          : await this.api.list(PAGE_SIZE, offset, sport);
      if (result.kind === 'forbidden') {
        return 'signed_out';
      }
      const { count, results } = result.page;
      if (results.length === 0 && offset > 0 && count > 0) {
        // The page is gone (its last activity was deleted): show the new last page.
        return this.fetch(Math.floor((count - 1) / PAGE_SIZE) * PAGE_SIZE);
      }
      this.page.set(result.page);
      this.offset.set(offset);
      return 'ok';
    } catch {
      return 'failed';
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
