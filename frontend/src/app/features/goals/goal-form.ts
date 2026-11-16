import {
  AfterViewInit,
  Component,
  ElementRef,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { GoalsApi } from '../../core/goals/goals-api';
import {
  Discipline,
  Goal,
  GoalChanges,
  GoalInput,
  GoalKind,
  GoalMetric,
  GoalPriority,
} from '../../core/goals/goals-models';
import { formatDuration } from '../activities/activity-format';
import { inputText, parseThreshold } from '../athlete/athlete-format';
import {
  DISCIPLINE_LABELS,
  DISTANCE_PRESETS,
  KIND_LABELS,
  PRIORITY_LABELS,
  kilometresText,
  parseDistanceKm,
  parseTargetTime,
} from './goal-format';

const TITLE_MAX = 100;
const NOTES_MAX = 1000;
const FALLBACK = 'Something went wrong. Please try again.';
/** The choice in the distance menu that opens the field for any other distance. */
const OTHER = 'other';

/** The names of the fields as the form knows them, for the messages next to them. */
const SERVER_FIELDS: Record<string, string> = {
  title: 'title',
  notes: 'notes',
  priority: 'priority',
  kind: 'kind',
  target_date: 'date',
  discipline: 'discipline',
  distance_m: 'distance',
  target_time_seconds: 'time',
  metric: 'metric',
  target_value: 'value',
};

/**
 * Adds a goal, or changes one (`goal` set). The fields depend on the kind; the kind of an
 * existing goal cannot be changed. What is checked here is what the server checks too, so that
 * the message appears next to the field without a round trip; the server's own messages are shown
 * the same way. Saving is one request at a time.
 */
@Component({
  selector: 'app-goal-form',
  templateUrl: './goal-form.html',
  styleUrls: ['../auth/auth-form.css', './goal-form.css'],
})
export class GoalForm implements OnInit, AfterViewInit {
  private readonly api = inject(GoalsApi);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  /** The goal to change, or `null` to add one. */
  readonly goal = input<Goal | null>(null);
  /** The goal as the server saved it. */
  readonly saved = output<Goal>();
  readonly cancelled = output<void>();
  /** The session is gone. */
  readonly signedOut = output<void>();
  /** The goal being changed does not exist any more. */
  readonly gone = output<void>();

  protected readonly kind = signal<GoalKind>('race');
  protected readonly title = signal('');
  protected readonly notes = signal('');
  protected readonly priority = signal<GoalPriority>('secondary');
  protected readonly date = signal('');
  protected readonly discipline = signal<Discipline | ''>('');
  /** '' (no distance), a preset in metres, or `OTHER`. */
  protected readonly distanceChoice = signal('');
  protected readonly distanceKm = signal('');
  protected readonly time = signal('');
  protected readonly metric = signal<GoalMetric>('ftp');
  protected readonly value = signal('');

  protected readonly busy = signal(false);
  /** Messages by field; `form` is for everything that concerns the whole goal. */
  protected readonly errors = signal<Record<string, string>>({});

  protected readonly kinds = Object.entries(KIND_LABELS);
  protected readonly kindLabel = KIND_LABELS;
  protected readonly disciplines = Object.entries(DISCIPLINE_LABELS);
  /** C, the preparation race, is only for a race. */
  protected readonly priorities = computed(() =>
    Object.entries(PRIORITY_LABELS).filter(
      ([value]) => value !== 'preparation' || this.kind() === 'race',
    ),
  );
  protected readonly presets = computed(() => {
    const discipline = this.discipline();
    return discipline ? DISTANCE_PRESETS[discipline] : [];
  });
  protected readonly other = OTHER;

  /** Another kind than a race cannot be a preparation race, so that choice is taken back. */
  protected setKind(kind: GoalKind): void {
    this.kind.set(kind);
    if (kind !== 'race' && this.priority() === 'preparation') {
      this.priority.set('secondary');
    }
  }

  ngOnInit(): void {
    const goal = this.goal();
    if (goal === null) {
      return;
    }
    this.kind.set(goal.kind);
    this.title.set(goal.title);
    this.notes.set(goal.notes);
    this.priority.set(goal.priority);
    this.date.set(goal.target_date ?? '');
    this.discipline.set(goal.discipline ?? '');
    if (goal.distance_m !== null) {
      const preset = goal.discipline
        ? DISTANCE_PRESETS[goal.discipline].find((entry) => entry.meters === goal.distance_m)
        : undefined;
      this.distanceChoice.set(preset ? String(preset.meters) : OTHER);
      this.distanceKm.set(kilometresText(goal.distance_m));
    }
    this.time.set(
      goal.target_time_seconds === null ? '' : formatDuration(goal.target_time_seconds),
    );
    if (goal.metric) {
      this.metric.set(goal.metric);
      this.value.set(goal.target_value === null ? '' : inputText(goal.metric, goal.target_value));
    }
  }

  ngAfterViewInit(): void {
    // The form opens somewhere above or below the user's eyes; the title is where to begin.
    this.host.nativeElement.querySelector<HTMLInputElement>('#goal-title')?.focus();
  }

  protected read(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected chooseDiscipline(event: Event): void {
    const discipline = this.read(event) as Discipline | '';
    this.discipline.set(discipline);
    // A preset belongs to one discipline: a choice that is not offered any more is dropped.
    const choice = this.distanceChoice();
    const offered = this.presets().some((entry) => String(entry.meters) === choice);
    if (choice !== '' && choice !== OTHER && !offered) {
      this.distanceChoice.set('');
    }
  }

  protected chooseDistance(event: Event): void {
    this.distanceChoice.set(this.read(event));
    this.distanceKm.set('');
  }

  protected cancel(): void {
    this.cancelled.emit();
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy()) {
      return;
    }
    const built = this.build();
    if (built === null) {
      return;
    }
    this.busy.set(true);
    try {
      const goal = this.goal();
      const result =
        goal === null
          ? await this.api.create(built)
          : await this.api.update(goal.id, withoutKind(built));
      switch (result.kind) {
        case 'ok':
          this.saved.emit(result.goal);
          break;
        case 'invalid':
          this.errors.set(serverMessages(result.fields, result.errors));
          break;
        case 'not_found':
          this.gone.emit();
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
    } catch {
      this.errors.set({ form: FALLBACK });
    } finally {
      this.busy.set(false);
    }
  }

  /** The request for what is in the form, or `null` (with the messages set) if it is unusable. */
  private build(): GoalInput | null {
    const errors: Record<string, string> = {};
    const title = this.title().trim();
    if (!title) {
      errors['title'] = 'Enter a title.';
    } else if (title.length > TITLE_MAX) {
      errors['title'] = `Use at most ${TITLE_MAX} characters.`;
    }
    if (this.notes().length > NOTES_MAX) {
      errors['notes'] = `Use at most ${NOTES_MAX} characters.`;
    }

    const kind = this.kind();
    const input: GoalInput = {
      kind,
      title,
      notes: this.notes(),
      priority: this.priority(),
      target_date: this.date() || null,
    };
    if (kind === 'race') {
      this.addRace(input, errors);
    } else if (kind === 'threshold') {
      this.addThreshold(input, errors);
    }
    this.errors.set(errors);
    return Object.keys(errors).length === 0 ? input : null;
  }

  private addRace(input: GoalInput, errors: Record<string, string>): void {
    const discipline = this.discipline();
    if (!discipline) {
      errors['discipline'] = 'Choose a discipline.';
    } else {
      input.discipline = discipline;
    }
    if (!this.date()) {
      errors['date'] = 'Enter the date of the race.';
    }

    const choice = this.distanceChoice();
    input.distance_m = null;
    if (choice === OTHER) {
      const km = parseDistanceKm(this.distanceKm());
      if (km.ok) {
        input.distance_m = km.value;
      } else {
        errors['distance'] = km.error;
      }
    } else if (choice !== '') {
      input.distance_m = Number(choice);
    }

    const time = parseTargetTime(this.time());
    if (time.ok) {
      input.target_time_seconds = time.value;
    } else {
      errors['time'] = time.error;
    }
  }

  private addThreshold(input: GoalInput, errors: Record<string, string>): void {
    input.metric = this.metric();
    const value = parseThreshold(this.metric(), this.value());
    if (value.ok) {
      input.target_value = value.value;
    } else {
      errors['value'] = value.error;
    }
  }
}

function withoutKind(input: GoalInput): GoalChanges {
  const changes: Partial<GoalInput> = { ...input };
  delete changes.kind;
  return changes;
}

/** The server's messages by the form's field names; the rest goes to the form as a whole. */
function serverMessages(fields: Record<string, string[]>, all: string[]): Record<string, string> {
  const messages: Record<string, string> = {};
  for (const [name, texts] of Object.entries(fields)) {
    const field = SERVER_FIELDS[name] ?? 'form';
    messages[field] = [messages[field], ...texts].filter(Boolean).join(' ');
  }
  return Object.keys(messages).length ? messages : { form: all.join(' ') };
}
