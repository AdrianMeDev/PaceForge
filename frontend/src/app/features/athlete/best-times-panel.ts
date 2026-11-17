import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { AthleteApi } from '../../core/athlete/athlete-api';
import { AthleteProfile, BestTimeDistance } from '../../core/athlete/athlete-models';
import {
  BestTimeDraft,
  DISTANCES,
  DISTANCE_LABELS,
  draftOf,
  inputOf,
  standing,
  todayText,
} from './best-times-format';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That distance does not exist any more.';

/**
 * The running best times: one per distance, the time and the day of the race. The newest one of the
 * last twelve months gives a VDOT and from it the threshold pace, which counts after a value the
 * user typed in. A time is saved or removed on its own; the page then shows the new pace and
 * zones. One action at a time.
 */
@Component({
  selector: 'app-best-times-panel',
  templateUrl: './best-times-panel.html',
  styleUrl: '../auth/auth-form.css',
})
export class BestTimesPanel implements OnInit {
  private readonly api = inject(AthleteApi);

  /** The profile that is shown: its times and the VDOT that counts. */
  readonly profile = input.required<AthleteProfile>();
  /** The profile as the server answered after a change. */
  readonly changed = output<AthleteProfile>();
  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly drafts = signal<Record<BestTimeDistance, BestTimeDraft>>(emptyDrafts());
  protected readonly busy = signal<BestTimeDistance | null>(null);
  /** The messages of the fields of each distance, by field name. */
  protected readonly fieldErrors = signal<
    Partial<Record<BestTimeDistance, Record<string, string>>>
  >({});
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);

  protected readonly distances = DISTANCES;
  protected readonly labels = DISTANCE_LABELS;
  protected readonly standing = standing;
  protected readonly rows = computed(() =>
    DISTANCES.map((distance) => ({
      distance,
      label: DISTANCE_LABELS[distance],
      stored: this.profile().best_times[distance],
    })),
  );
  protected readonly counting = computed(() => {
    const found = this.profile().vdot;
    return found === null ? null : { ...found, label: DISTANCE_LABELS[found.distance] };
  });

  ngOnInit(): void {
    const times = this.profile().best_times;
    this.drafts.set(
      Object.fromEntries(
        DISTANCES.map((distance) => [distance, draftOf(times[distance])]),
      ) as Record<BestTimeDistance, BestTimeDraft>,
    );
  }

  protected readValue(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected set(distance: BestTimeDistance, field: keyof BestTimeDraft, value: string): void {
    this.drafts.update((current) => ({
      ...current,
      [distance]: { ...current[distance], [field]: value },
    }));
  }

  protected async save(distance: BestTimeDistance, event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy() !== null) {
      return;
    }
    this.clearMessages();
    const checked = inputOf(this.drafts()[distance], todayText());
    if (!checked.ok) {
      this.fieldErrors.set({ [distance]: 'errors' in checked ? checked.errors : {} });
      return;
    }
    this.busy.set(distance);
    try {
      const result = await this.api.setBestTime(distance, checked.value);
      switch (result.kind) {
        case 'ok':
          this.afterChange(distance, result.profile, 'Saved.');
          break;
        case 'invalid':
          this.fieldErrors.set({
            [distance]: Object.fromEntries(
              Object.entries(result.fields)
                .filter(([name]) => name === 'seconds' || name === 'date')
                .map(([name, texts]) => [name, texts.join(' ')]),
            ),
          });
          this.errors.set(
            Object.keys(result.fields).length
              ? Object.entries(result.fields)
                  .filter(([name]) => name !== 'seconds' && name !== 'date')
                  .flatMap(([, texts]) => texts)
              : result.errors,
          );
          break;
        case 'not_found':
          this.errors.set([GONE]);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(null);
    }
  }

  protected async remove(distance: BestTimeDistance): Promise<void> {
    if (this.busy() !== null) {
      return;
    }
    this.clearMessages();
    this.busy.set(distance);
    try {
      const result = await this.api.clearBestTime(distance);
      switch (result.kind) {
        case 'ok':
          this.afterChange(distance, result.profile, 'Removed.');
          break;
        case 'not_found':
          this.errors.set([GONE]);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(null);
    }
  }

  /** The draft of the changed distance shows what is stored now; the others stay as typed. */
  private afterChange(distance: BestTimeDistance, profile: AthleteProfile, text: string): void {
    this.drafts.update((current) => ({
      ...current,
      [distance]: draftOf(profile.best_times[distance]),
    }));
    this.notice.set(text);
    this.changed.emit(profile);
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.fieldErrors.set({});
    this.notice.set(null);
  }
}

function emptyDrafts(): Record<BestTimeDistance, BestTimeDraft> {
  return Object.fromEntries(
    DISTANCES.map((distance) => [distance, { time: '', date: '' }]),
  ) as Record<BestTimeDistance, BestTimeDraft>;
}
