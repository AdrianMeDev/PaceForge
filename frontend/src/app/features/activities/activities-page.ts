import { DOCUMENT, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ActivitiesApi } from '../../core/activities/activities-api';
import {
  Activity,
  ActivityPage,
  ImportActivityResult,
} from '../../core/activities/activities-models';
import {
  formatDistance,
  formatDuration,
  formatHeartRate,
  formatLoad,
  formatRpe,
  sourceLabel,
  sportLabel,
} from './activity-format';
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
 * Where users bring FIT and TCX files in and see what was imported. The server decides by the
 * content of a file, never by its name; files are sent one after the other so that each gets its
 * own result and one failure does not stop the others.
 */
@Component({
  selector: 'app-activities-page',
  imports: [RouterLink, DatePipe, ManualActivityForm],
  templateUrl: './activities-page.html',
  styleUrls: ['../auth/auth-form.css', './activities-page.css'],
})
export class ActivitiesPage implements OnInit {
  private readonly api = inject(ActivitiesApi);
  private readonly document = inject(DOCUMENT);

  protected readonly view = signal<View>('loading');
  protected readonly page = signal<ActivityPage>({ count: 0, results: [] });
  protected readonly offset = signal(0);
  /** An import or a deletion is running: nothing else may start. */
  protected readonly busy = signal(false);
  /** The list is being fetched again (paging, after an import or a deletion). */
  protected readonly refreshing = signal(false);
  protected readonly currentFile = signal<string | null>(null);
  protected readonly results = signal<FileResult[]>([]);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  protected readonly confirming = signal<string | null>(null);
  protected readonly highlighted = signal<string | null>(null);

  protected readonly first = computed(() => (this.page().results.length ? this.offset() + 1 : 0));
  protected readonly last = computed(() => this.offset() + this.page().results.length);
  protected readonly hasPrevious = computed(() => this.offset() > 0);
  protected readonly hasNext = computed(() => this.last() < this.page().count);
  protected readonly previousOffset = computed(() => Math.max(0, this.offset() - PAGE_SIZE));
  protected readonly nextOffset = computed(() => this.offset() + PAGE_SIZE);
  protected readonly listedIds = computed(() => this.page().results.map((a) => a.id));

  protected readonly sport = sportLabel;
  protected readonly source = sourceLabel;
  protected readonly distance = formatDistance;
  protected readonly heartRate = formatHeartRate;
  protected readonly rpeText = formatRpe;
  protected readonly loadText = formatLoad;
  protected readonly duration = (activity: Activity): string =>
    formatDuration(activity.timer_seconds ?? activity.elapsed_seconds);

  ngOnInit(): Promise<void> {
    return this.load();
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
    this.confirming.set(activity.id);
  }

  protected cancelDelete(): void {
    this.confirming.set(null);
  }

  protected async delete(activity: Activity): Promise<void> {
    if (this.busy()) {
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
      const result = await this.api.list(PAGE_SIZE, offset);
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
