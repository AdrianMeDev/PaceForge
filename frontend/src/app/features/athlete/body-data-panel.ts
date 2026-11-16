import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { AthleteApi } from '../../core/athlete/athlete-api';
import {
  AthleteProfile,
  Equipment,
  Sex,
  StrengthExperience,
  TrainingSport,
} from '../../core/athlete/athlete-models';
import {
  BODY_FIELDS,
  BodyDraft,
  BodyErrors,
  EQUIPMENT_LABELS,
  EXPERIENCE_LABELS,
  SEX_LABELS,
  TRAINING_SPORT_LABELS,
  changesOf,
  draftOf,
  emptyDraft,
} from './body-data-format';

const FALLBACK = 'Something went wrong. Please try again.';
/**
 * What the user tells about their body and their training: year of birth, sex, weight, resting
 * heart rate, years of training per sport, experience with strength training and the equipment
 * for it. Everything is optional and an empty field clears what is stored. The values go to the
 * AI coach as numbers and fixed words (the age, never the year of birth), and the panel says to
 * which provider.
 */
@Component({
  selector: 'app-body-data-panel',
  templateUrl: './body-data-panel.html',
  styleUrls: ['../auth/auth-form.css', './body-data-panel.css'],
})
export class BodyDataPanel implements OnInit {
  private readonly api = inject(AthleteApi);

  /** The profile the form starts with. Later changes of the input do not overwrite the form. */
  readonly profile = input.required<AthleteProfile>();
  /** Where what is sent goes, in a few words (see `providerLine`). */
  readonly provider = input<string>('your AI provider');
  /** The profile as the server answered after a save. */
  readonly saved = output<AthleteProfile>();
  /** The session is gone. */
  readonly signedOut = output<void>();

  protected readonly draft = signal<BodyDraft>(emptyDraft());
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly fieldErrors = signal<BodyErrors>({});
  protected readonly notice = signal<string | null>(null);

  protected readonly sexes = Object.entries(SEX_LABELS) as [Sex, string][];
  protected readonly experiences = Object.entries(EXPERIENCE_LABELS) as [
    StrengthExperience,
    string,
  ][];
  protected readonly equipment = Object.entries(EQUIPMENT_LABELS) as [Equipment, string][];
  protected readonly sports = Object.entries(TRAINING_SPORT_LABELS) as [TrainingSport, string][];

  ngOnInit(): void {
    this.draft.set(draftOf(this.profile()));
  }

  protected readValue(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  protected set<K extends keyof BodyDraft>(name: K, value: BodyDraft[K]): void {
    this.draft.update((current) => ({ ...current, [name]: value }));
  }

  protected setYears(sport: TrainingSport, text: string): void {
    this.draft.update((current) => ({ ...current, years: { ...current.years, [sport]: text } }));
  }

  protected setEquipment(item: Equipment, ticked: boolean): void {
    this.draft.update((current) => {
      const rest = current.equipment.filter((candidate) => candidate !== item);
      return { ...current, equipment: ticked ? [...rest, item] : rest };
    });
  }

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    this.errors.set([]);
    this.fieldErrors.set({});
    this.notice.set(null);
    const checked = changesOf(this.draft(), new Date().getFullYear());
    if ('errors' in checked) {
      this.fieldErrors.set(checked.errors);
      return;
    }
    this.busy.set(true);
    try {
      const result = await this.api.saveBody(checked.changes);
      switch (result.kind) {
        case 'ok':
          this.draft.set(draftOf(result.profile));
          this.notice.set('Saved.');
          this.saved.emit(result.profile);
          break;
        case 'invalid':
          this.showServerMessages(result.fields, result.errors);
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

  /** The messages the server has for a field go under it; the rest goes above the form. */
  private showServerMessages(fields: Record<string, string[]>, all: string[]): void {
    const known = (name: string) => (BODY_FIELDS as readonly string[]).includes(name);
    this.fieldErrors.set(
      Object.fromEntries(
        Object.entries(fields)
          .filter(([name]) => known(name))
          .map(([name, texts]) => [name, texts.join(' ')]),
      ),
    );
    this.errors.set(
      Object.keys(fields).length
        ? Object.entries(fields)
            .filter(([name]) => !known(name))
            .flatMap(([, texts]) => texts)
        : all,
    );
  }
}
