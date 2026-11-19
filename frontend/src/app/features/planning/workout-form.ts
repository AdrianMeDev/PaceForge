import { Component, computed, input, linkedSignal, output, signal } from '@angular/core';
import { SegmentEditor } from './segment-editor';
import {
  EditedWorkout,
  Sport,
  WorkoutGoal,
  WorkoutSlot,
  ZoneSystem,
} from '../../core/planning/planning-models';
import {
  GOAL_CHOICES,
  NOTES_MAX,
  SegmentDraft,
  SegmentRowError,
  SLOT_CHOICES,
  SPORT_CHOICES,
  TITLE_MAX,
  ZONE_SYSTEMS_OF,
  blankWorkout,
  checkNotes,
  checkTitle,
  dayChoices,
  draftsFromSegments,
  parseDuration,
  parseSegmentDrafts,
  parseSegmentDuration,
  parseSegmentRepeat,
  parseStretching,
  sanitizeSegmentZones,
  zoneChoices,
  zoneSystemChoices,
} from './edit-format';
import { minutesText } from './plan-format';

type Field = 'title' | 'duration' | 'zone' | 'notes' | 'stretching';

/**
 * Change one workout of a plan, or add one. What is checked here is what the server checks too,
 * so that the message stands next to the field; the checks of the plan as a whole (is there time
 * on that day?) come from the server after the workout is saved. Moving a workout is changing its
 * day and its time of day. The input stays in the form after a refusal.
 *
 * The interval structure is edited in the form, and the duration of a workout with one follows it
 * as it is edited; removing the structure frees the duration. A strength workout has none: the
 * structure is hidden, and removed when the workout is saved as strength. The `lineage` of the workout is kept as it is: it is what tells
 * a workout that was moved from a new one.
 */
@Component({
  selector: 'app-workout-form',
  imports: [SegmentEditor],
  templateUrl: './workout-form.html',
  styleUrl: './workout-form.css',
})
export class WorkoutForm {
  /** The Monday of the week of the plan, `YYYY-MM-DD`. */
  readonly week = input.required<string>();
  /** The workout to change, or `null` for a new one. */
  readonly workout = input<EditedWorkout | null>(null);
  /** The day a new workout starts on (a day of the week); the first day of the week if none. */
  readonly day = input<string | null>(null);
  /** The workout as the user wants it. */
  readonly saved = output<EditedWorkout>();
  readonly cancelled = output<void>();

  protected readonly titleMax = TITLE_MAX;
  protected readonly notesMax = NOTES_MAX;
  protected readonly sports = SPORT_CHOICES;
  protected readonly goals = GOAL_CHOICES;
  protected readonly slots = SLOT_CHOICES;
  protected readonly days = computed(() => dayChoices(this.week()));
  protected readonly minutes = minutesText;
  protected readonly zones = zoneChoices;

  // What the form starts from; the fields below follow it until the user types.
  protected readonly start = computed(
    () => this.workout() ?? blankWorkout(this.day() ?? this.week()),
  );
  protected readonly isNew = computed(() => this.workout() === null);
  protected readonly dayValue = linkedSignal(() => this.start().day);
  protected readonly slotValue = linkedSignal<string>(() => this.start().slot ?? '');
  protected readonly sportValue = linkedSignal<Sport>(() => this.start().sport);
  protected readonly titleValue = linkedSignal(() => this.start().title);
  protected readonly goalValue = linkedSignal<WorkoutGoal>(() => this.start().goal);
  protected readonly durationValue = linkedSignal(() => String(this.start().duration_minutes));
  protected readonly zoneSystemValue = linkedSignal<string>(() => this.start().zone_system ?? '');
  protected readonly zoneValue = linkedSignal(() => String(this.start().zone ?? ''));
  protected readonly notesValue = linkedSignal(() => this.start().notes);
  protected readonly stretchingValue = linkedSignal(() =>
    this.start().stretching_minutes === 0 ? '' : String(this.start().stretching_minutes),
  );
  protected readonly segmentRows = linkedSignal<SegmentDraft[]>(() =>
    draftsFromSegments(this.start().segments),
  );
  // Whether the user tried to save; the messages of the rows show from then on.
  private readonly attempted = linkedSignal(() => {
    this.start();
    return false;
  });

  protected readonly errors = signal<Partial<Record<Field, string>>>({});

  /** Whether the rows are the structure of the workout: a strength workout has none. */
  protected readonly keepsStructure = computed(
    () => this.segmentRows().length > 0 && this.sportValue() !== 'strength',
  );
  /** Whether the structure is dropped because the sport is strength. */
  protected readonly structureRemoved = computed(
    () => this.segmentRows().length > 0 && this.sportValue() === 'strength',
  );
  protected readonly segmentChecks = computed(() => {
    if (!this.attempted() || !this.keepsStructure()) {
      return { rows: [] as SegmentRowError[], total: null };
    }
    const parsed = parseSegmentDrafts(this.segmentRows());
    return parsed.ok ? { rows: [], total: null } : { rows: parsed.rowErrors, total: parsed.error };
  });
  /** The duration of the rows that can be read, in minutes. */
  protected readonly structureMinutes = computed(() => segmentRowsMinutes(this.segmentRows()));
  /** What to tell about the exercises: none to tell, kept as they are, or removed with the sport. */
  protected readonly exercisesHint = computed<'none' | 'kept' | 'removed'>(() => {
    if (this.start().exercises.length === 0) {
      return 'none';
    }
    return this.sportValue() === 'strength' ? 'kept' : 'removed';
  });
  protected readonly exerciseCount = computed(() => this.start().exercises.length);
  protected readonly zoneSystems = computed(() => zoneSystemChoices(this.sportValue()));
  protected readonly zoneSystem = computed<ZoneSystem | null>(() => {
    const system = this.zoneSystemValue();
    return system === '' ? null : (system as ZoneSystem);
  });

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected setSport(value: string): void {
    const sport = value as Sport;
    this.sportValue.set(sport);
    if (sport !== 'strength') {
      this.segmentRows.update((rows) => sanitizeSegmentZones(rows, sport));
    }
    if (!ZONE_SYSTEMS_OF[sport].includes(this.zoneSystem() as ZoneSystem)) {
      this.setZoneSystem('');
    }
  }

  protected setZoneSystem(value: string): void {
    this.zoneSystemValue.set(value);
    this.zoneValue.set('');
  }

  /** Take the rows as they are edited; when the last one goes, the duration stays as it was. */
  protected setSegmentRows(rows: SegmentDraft[]): void {
    if (rows.length === 0 && this.keepsStructure()) {
      this.durationValue.set(String(this.structureMinutes()));
    }
    this.segmentRows.set(rows);
  }

  protected submit(): void {
    this.attempted.set(true);
    const errors: Partial<Record<Field, string>> = {};
    const title = checkTitle(this.titleValue());
    const notes = checkNotes(this.notesValue());
    const segments = this.keepsStructure() ? parseSegmentDrafts(this.segmentRows()) : null;
    const duration =
      segments === null
        ? parseDuration(this.durationValue())
        : segments.ok
          ? { ok: true as const, value: segmentRowsMinutes(this.segmentRows()) }
          : { ok: false as const, error: '' };
    const stretching = parseStretching(this.stretchingValue());
    if (title !== null) {
      errors.title = title;
    }
    if (notes !== null) {
      errors.notes = notes;
    }
    if (!duration.ok && segments === null) {
      errors.duration = duration.error;
    }
    if (!stretching.ok) {
      errors.stretching = stretching.error;
    }
    if (this.zoneSystem() !== null && this.zoneValue() === '') {
      errors.zone = 'Choose a zone.';
    }
    this.errors.set(errors);
    if (!duration.ok || !stretching.ok || Object.keys(errors).length > 0) {
      return;
    }
    const system = this.zoneSystem();
    this.saved.emit({
      lineage: this.start().lineage,
      day: this.dayValue(),
      sport: this.sportValue(),
      title: this.titleValue().trim(),
      goal: this.goalValue(),
      duration_minutes: duration.value,
      zone_system: system,
      zone: system === null ? null : Number(this.zoneValue()),
      notes: this.notesValue().trim(),
      slot: this.slotValue() === '' ? null : (this.slotValue() as WorkoutSlot),
      stretching_minutes: stretching.value,
      segments: segments?.ok ? segments.segments : [],
      // The exercises belong to a strength workout: they stay with it and go with another sport.
      exercises: this.sportValue() === 'strength' ? this.start().exercises : [],
    });
  }
}

/** The minutes of the rows that can be read, repeats counted; the same sum as on the server. */
function segmentRowsMinutes(rows: readonly SegmentDraft[]): number {
  let seconds = 0;
  for (const row of rows) {
    const duration = parseSegmentDuration(row.duration);
    const repeat = parseSegmentRepeat(row.repeat);
    if (duration.ok && repeat.ok) {
      seconds += duration.value * repeat.value;
    }
  }
  return seconds === 0 ? 0 : Math.max(1, Math.round(seconds / 60));
}
