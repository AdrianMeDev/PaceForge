import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, output, signal, viewChild } from '@angular/core';
import { AvailabilityApi } from '../../core/availability/availability-api';
import { Period } from '../../core/availability/availability-models';
import { PERIOD_KIND_LABELS, formatPeriodLength } from './availability-format';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { PeriodForm } from './period-form';

type View = 'loading' | 'unreachable' | 'ready';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That period does not exist any more.';
const REFRESH_FAILED = 'The list could not be refreshed. Please try again.';

/**
 * The periods in which the user cannot train, in the order the server sends them (going on and
 * coming ones first, then the past ones). Periods are added through a form and removed after a
 * question; the list is fetched again after every change. One action at a time.
 */
@Component({
  selector: 'app-periods-panel',
  imports: [DatePipe, ConfirmDialog, PeriodForm],
  templateUrl: './periods-panel.html',
  styleUrls: ['../auth/auth-form.css', './periods-panel.css'],
})
export class PeriodsPanel implements OnInit {
  private readonly api = inject(AvailabilityApi);

  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly view = signal<View>('loading');
  protected readonly periods = signal<Period[]>([]);
  protected readonly adding = signal(false);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The id of the period that is about to be deleted, waiting for the answer to the question. */
  /** The period the dialog asks about. */
  protected readonly confirming = signal<Period | null>(null);
  private readonly deleteDialog = viewChild(ConfirmDialog);

  protected readonly kindLabel = PERIOD_KIND_LABELS;
  protected readonly lengthText = formatPeriodLength;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.listPeriods();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.periods.set(result.periods);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected openAdd(): void {
    this.clearMessages();
    this.confirming.set(null);
    this.adding.set(true);
  }

  protected closeAdd(): void {
    this.adding.set(false);
  }

  protected async added(): Promise<void> {
    this.adding.set(false);
    this.clearMessages();
    this.notice.set('The period was added.');
    await this.refresh();
  }

  protected askDelete(period: Period): void {
    this.clearMessages();
    this.confirming.set(period);
    this.deleteDialog()?.open();
  }

  /** The dialog was answered with "Delete period". */
  protected async delete(): Promise<void> {
    const period = this.confirming();
    if (this.busy() || period === null) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.deletePeriod(period.id);
      this.confirming.set(null);
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.notice.set(result.kind === 'deleted' ? 'The period was deleted.' : GONE);
      await this.refresh();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** Fetches the list again without leaving the page; a failure is shown above the list. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.api.listPeriods();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.periods.set(result.periods);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
