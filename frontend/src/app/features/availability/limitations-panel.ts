import { Component, OnInit, inject, viewChild, input, output, signal } from '@angular/core';
import { AvailabilityApi } from '../../core/availability/availability-api';
import {
  AvailabilitySport,
  BodyPart,
  Limitation,
} from '../../core/availability/availability-models';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { UNKNOWN_PROVIDER } from './provider-line';

type View = 'loading' | 'unreachable' | 'ready';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That entry does not exist any more.';
const REFRESH_FAILED = 'The list could not be refreshed. Please try again.';

/** The body parts to choose from, in the order the server lists them. */
export const BODY_PART_LABELS: Record<BodyPart, string> = {
  foot: 'Foot',
  ankle: 'Ankle',
  achilles: 'Achilles tendon',
  calf: 'Calf',
  shin: 'Shin',
  knee: 'Knee',
  thigh: 'Thigh',
  hip: 'Hip',
  back: 'Back',
  shoulder: 'Shoulder',
  other: 'Other',
};
const BODY_PARTS = Object.keys(BODY_PART_LABELS) as BodyPart[];

/** The sports an entry can affect, in the order the server keeps them. */
const SPORTS: { value: AvailabilitySport; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'cycling', label: 'Cycling' },
  { value: 'swimming', label: 'Swimming' },
  { value: 'strength', label: 'Strength / gym' },
];

/** The sports of an entry in words; none means no particular sport. */
export function sportsText(sports: readonly AvailabilitySport[]): string {
  return sports.length === 0
    ? 'No particular sport'
    : SPORTS.filter((sport) => sports.includes(sport.value))
        .map((sport) => sport.label)
        .join(', ');
}

/**
 * The user's injuries and limitations: where it is, the sports it affects, and whether it is
 * current or healed. Current entries go to the AI coach as a body part and sports, without any
 * text, and the page says to which provider. Entries are added with a small form, marked as
 * healed (or current again) and deleted after a question; the list is fetched again after every
 * change. One action at a time.
 */
@Component({
  selector: 'app-limitations-panel',
  imports: [ConfirmDialog],
  templateUrl: './limitations-panel.html',
  styleUrl: './limitations-panel.css',
})
export class LimitationsPanel implements OnInit {
  private readonly api = inject(AvailabilityApi);

  /** Where the entries go, in a few words (see `providerLine`). */
  readonly provider = input<string>(UNKNOWN_PROVIDER);
  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly view = signal<View>('loading');
  protected readonly limitations = signal<Limitation[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The id of the entry about to be deleted, waiting for the answer to the question. */
  /** The entry the dialog asks about. */
  protected readonly confirming = signal<Limitation | null>(null);
  private readonly deleteDialog = viewChild(ConfirmDialog);

  protected readonly bodyPart = signal<BodyPart>('knee');
  protected readonly sports = signal<AvailabilitySport[]>([]);
  protected readonly bodyPartError = signal<string | null>(null);
  protected readonly sportsError = signal<string | null>(null);

  protected readonly bodyParts = BODY_PARTS;
  protected readonly bodyPartLabels = BODY_PART_LABELS;
  protected readonly sportChoices = SPORTS;
  protected readonly sportsOf = sportsText;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.listLimitations();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.limitations.set(result.limitations);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected setSport(sport: AvailabilitySport, ticked: boolean): void {
    this.sports.update((list) => {
      const rest = list.filter((candidate) => candidate !== sport);
      return ticked ? [...rest, sport] : rest;
    });
  }

  protected readValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }

  protected isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  protected async add(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const sports = SPORTS.map((sport) => sport.value).filter((sport) =>
        this.sports().includes(sport),
      );
      const result = await this.api.createLimitation({ body_part: this.bodyPart(), sports });
      switch (result.kind) {
        case 'ok':
          this.sports.set([]);
          this.notice.set('The entry was added.');
          await this.refresh();
          break;
        case 'invalid':
          this.bodyPartError.set(result.fields['body_part']?.join(' ') ?? null);
          this.sportsError.set(result.fields['sports']?.join(' ') ?? null);
          // What no field owns (the limit of entries, say) is shown above the form.
          this.errors.set(
            Object.keys(result.fields).length
              ? Object.entries(result.fields)
                  .filter(([name]) => name !== 'body_part' && name !== 'sports')
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

  protected async setStatus(entry: Limitation, healed: boolean): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.confirming.set(null);
    this.busy.set(true);
    try {
      const result = await this.api.updateLimitation(entry.id, {
        status: healed ? 'healed' : 'current',
      });
      switch (result.kind) {
        case 'ok':
          this.notice.set(healed ? 'Marked as healed.' : 'Marked as current again.');
          await this.refresh();
          break;
        case 'not_found':
          this.notice.set(GONE);
          await this.refresh();
          break;
        case 'invalid':
          this.errors.set(result.errors);
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

  protected askDelete(entry: Limitation): void {
    this.clearMessages();
    this.confirming.set(entry);
    this.deleteDialog()?.open();
  }

  /** The dialog was answered with "Delete entry". */
  protected async delete(): Promise<void> {
    const entry = this.confirming();
    if (this.busy() || entry === null) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.deleteLimitation(entry.id);
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
      const result = await this.api.listLimitations();
      if (result.kind === 'forbidden') {
        this.signedOut.emit();
        return;
      }
      this.limitations.set(result.limitations);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
    this.bodyPartError.set(null);
    this.sportsError.set(null);
  }
}
