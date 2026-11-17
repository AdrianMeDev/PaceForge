import { Component, OnInit, inject, viewChild, output, signal } from '@angular/core';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  AvailabilitySlot,
  AvailabilitySport,
  FixedSession,
  Weekday,
} from '../../core/availability/availability-models';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { WEEKDAY_NAMES } from './availability-format';

type View = 'loading' | 'unreachable' | 'ready';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That entry does not exist any more.';
const REFRESH_FAILED = 'The list could not be refreshed. Please try again.';
/** The fields the form shows an error under; anything else goes above the form. */
const FIELDS = ['weekday', 'sport', 'minutes', 'slot'];

const SPORTS: { value: AvailabilitySport; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'cycling', label: 'Cycling' },
  { value: 'swimming', label: 'Swimming' },
  { value: 'strength', label: 'Strength / gym' },
];
const SLOTS: { value: AvailabilitySlot; label: string }[] = [
  { value: 'morning', label: 'Morning' },
  { value: 'afternoon', label: 'Afternoon' },
  { value: 'evening', label: 'Evening' },
];
const WEEKDAYS: Weekday[] = [0, 1, 2, 3, 4, 5, 6];

/** An entry in words: "Tuesday · Running · 60 min · Evening". */
export function sessionText(session: FixedSession): string {
  const sport = SPORTS.find((choice) => choice.value === session.sport)?.label ?? session.sport;
  const slot = SLOTS.find((choice) => choice.value === session.slot)?.label;
  return [WEEKDAY_NAMES[session.weekday], sport, `${session.minutes} min`, slot]
    .filter((part) => part)
    .join(' · ');
}

/**
 * The sessions that happen every week at a fixed time (a running club, a class): weekday, sport,
 * how long and, if the user wants, the part of the day. The coach is told to plan them, and the
 * checks warn when a plan has none of them. Entries are added with a small form and deleted
 * after a question; the list is fetched again after every change. One action at a time.
 */
@Component({
  selector: 'app-fixed-sessions-panel',
  imports: [ConfirmDialog],
  templateUrl: './fixed-sessions-panel.html',
  styleUrls: ['../auth/auth-form.css', './fixed-sessions-panel.css'],
})
export class FixedSessionsPanel implements OnInit {
  private readonly api = inject(AvailabilityApi);

  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly view = signal<View>('loading');
  protected readonly sessions = signal<FixedSession[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The id of the entry about to be deleted, waiting for the answer to the question. */
  /** The entry the dialog asks about. */
  protected readonly confirming = signal<FixedSession | null>(null);
  private readonly deleteDialog = viewChild(ConfirmDialog);

  protected readonly weekday = signal<Weekday>(1);
  protected readonly sport = signal<AvailabilitySport>('running');
  protected readonly minutes = signal('60');
  protected readonly slot = signal<AvailabilitySlot | ''>('');
  protected readonly fieldErrors = signal<Record<string, string>>({});

  protected readonly weekdays = WEEKDAYS;
  protected readonly weekdayNames = WEEKDAY_NAMES;
  protected readonly sportChoices = SPORTS;
  protected readonly slotChoices = SLOTS;
  protected readonly describe = sessionText;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.listFixedSessions();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.sessions.set(result.sessions);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected readValue(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected toWeekday(value: string): Weekday {
    return WEEKDAYS.find((day) => String(day) === value) ?? 1;
  }

  protected async add(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    const text = this.minutes().trim();
    if (!/^\d+$/.test(text)) {
      this.fieldErrors.set({ minutes: 'Enter a whole number of minutes between 5 and 600.' });
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.api.createFixedSession({
        weekday: this.weekday(),
        sport: this.sport(),
        minutes: Number(text),
        slot: this.slot() || null,
      });
      switch (result.kind) {
        case 'ok':
          this.notice.set('The entry was added.');
          await this.refresh();
          break;
        case 'invalid':
          this.fieldErrors.set(
            Object.fromEntries(
              FIELDS.filter((name) => result.fields[name]).map((name) => [
                name,
                (result.fields[name] ?? []).join(' '),
              ]),
            ),
          );
          // What no field owns (the limit of entries, say) is shown above the form.
          this.errors.set(
            Object.keys(result.fields).length
              ? Object.entries(result.fields)
                  .filter(([name]) => !FIELDS.includes(name))
                  .flatMap(([, texts]) => texts)
              : result.errors,
          );
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected askDelete(session: FixedSession): void {
    this.clearMessages();
    this.confirming.set(session);
    this.deleteDialog()?.open();
  }

  /** The dialog was answered with "Delete entry". */
  protected async delete(): Promise<void> {
    const session = this.confirming();
    if (this.busy() || session === null) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.deleteFixedSession(session.id);
      this.confirming.set(null);
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.notice.set(result.kind === 'deleted' ? 'The entry was deleted.' : GONE);
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
      const result = await this.api.listFixedSessions();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.sessions.set(result.sessions);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
    this.fieldErrors.set({});
  }
}
