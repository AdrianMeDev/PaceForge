import { Component, inject, input, output, signal } from '@angular/core';
import { ActivitiesApi } from '../../core/activities/activities-api';
import { ManualField, Sport } from '../../core/activities/activities-models';
import {
  NOTES_MAX,
  RPE_CHOICES,
  SPORT_CHOICES,
  parseDistance,
  parseDuration,
  timeText,
  todayText,
} from './manual-activity-format';

const FALLBACK = 'Something went wrong. Please try again.';
const TOO_MANY = 'Too many entries. Please wait a minute and try again.';
const DUPLICATE = 'You already have this session.';
const NO_DATE = 'Enter the day of the session.';
const NO_TIME = 'Enter the time the session started.';
const NOTES_TOO_LONG = `Use at most ${NOTES_MAX} characters.`;

/**
 * Enter a session by hand: for what no watch recorded (strength training) and for the sessions that
 * only Strava has. What is checked here is what the server checks too, so that the message stands
 * next to the field; the server's own messages are shown the same way. The input stays in the form
 * after a refusal, and is cleared only when the session was saved.
 */
@Component({
  selector: 'app-manual-activity-form',
  templateUrl: './manual-activity-form.html',
  styleUrls: ['../auth/auth-form.css', './manual-activity-form.css'],
})
export class ManualActivityForm {
  private readonly api = inject(ActivitiesApi);

  /** The ids of the activities the list shows, so that "show it" is offered only for those. */
  readonly listedIds = input<readonly string[]>([]);
  /** Another action of the page is running: nothing may start. */
  readonly disabled = input(false);
  /** A session was saved. */
  readonly entered = output<void>();
  readonly signedOut = output<void>();
  /** The user wants to see the session they have already. */
  readonly locate = output<string>();

  protected readonly sports = SPORT_CHOICES;
  protected readonly ratings = RPE_CHOICES;
  protected readonly notesMax = NOTES_MAX;

  protected readonly sport = signal<Sport>('strength');
  protected readonly date = signal(todayText());
  protected readonly time = signal(timeText());
  protected readonly duration = signal('');
  protected readonly distance = signal('');
  protected readonly rpe = signal('');
  protected readonly notes = signal('');

  protected readonly errors = signal<Partial<Record<ManualField, string>>>({});
  protected readonly message = signal<string | null>(null);
  protected readonly saved = signal(false);
  protected readonly existingId = signal<string | null>(null);
  protected readonly saving = signal(false);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected async submit(): Promise<void> {
    if (this.saving() || this.disabled()) {
      return;
    }
    this.message.set(null);
    this.saved.set(false);
    this.existingId.set(null);
    const errors: Partial<Record<ManualField, string>> = {};
    const duration = parseDuration(this.duration());
    const distance = parseDistance(this.distance());
    if (!duration.ok) {
      errors.duration_minutes = duration.error;
    }
    if (!distance.ok) {
      errors.distance_km = distance.error;
    }
    if (this.date() === '') {
      errors.date = NO_DATE;
    }
    if (this.time() === '') {
      errors.time = NO_TIME;
    }
    if (this.notes().length > NOTES_MAX) {
      errors.notes = NOTES_TOO_LONG;
    }
    this.errors.set(errors);
    if (!duration.ok || !distance.ok || Object.keys(errors).length > 0) {
      return;
    }

    this.saving.set(true);
    try {
      const result = await this.api.enter({
        sport: this.sport(),
        date: this.date(),
        time: this.time(),
        duration_minutes: duration.value,
        distance_km: distance.value,
        rpe: this.rpe() === '' ? null : Number(this.rpe()),
        notes: this.notes().trim(),
      });
      switch (result.kind) {
        case 'entered':
          this.clear();
          this.saved.set(true);
          this.entered.emit();
          break;
        case 'duplicate':
          this.message.set(DUPLICATE);
          this.existingId.set(result.existingId);
          break;
        case 'invalid':
          this.errors.set(firstMessages(result.errors));
          this.message.set(result.message);
          break;
        case 'rate_limited':
          this.message.set(TOO_MANY);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.message.set(FALLBACK);
    } finally {
      this.saving.set(false);
    }
  }

  /** The entries that belong to one session are cleared; sport, day and the rest stay. */
  private clear(): void {
    this.errors.set({});
    this.duration.set('');
    this.distance.set('');
    this.rpe.set('');
    this.notes.set('');
    this.time.set(timeText());
  }
}

function firstMessages(
  errors: Partial<Record<ManualField, string[]>>,
): Partial<Record<ManualField, string>> {
  const first: Partial<Record<ManualField, string>> = {};
  for (const [field, messages] of Object.entries(errors) as [ManualField, string[]][]) {
    first[field] = messages[0];
  }
  return first;
}
