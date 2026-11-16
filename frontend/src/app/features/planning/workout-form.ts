import { Component, computed, input, linkedSignal, output, signal } from '@angular/core';
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
  SLOT_CHOICES,
  SPORT_CHOICES,
  TITLE_MAX,
  ZONE_SYSTEMS_OF,
  blankWorkout,
  checkNotes,
  checkTitle,
  dayChoices,
  parseDuration,
  parseStretching,
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
 * A workout with an interval structure keeps it, and its duration follows the structure; removing
 * the structure frees the duration. The `lineage` of the workout is kept as it is: it is what tells
 * a workout that was moved from a new one.
 */
@Component({
  selector: 'app-workout-form',
  templateUrl: './workout-form.html',
  styleUrls: ['../auth/auth-form.css', './workout-form.css'],
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
  protected readonly dropStructure = linkedSignal(() => {
    this.start();
    return false;
  });

  protected readonly errors = signal<Partial<Record<Field, string>>>({});

  /** Whether the workout has an interval structure that is kept. */
  protected readonly keepsStructure = computed(
    () => this.start().segments.length > 0 && !this.dropStructure(),
  );
  protected readonly hasStructure = computed(() => this.start().segments.length > 0);
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
    if (!ZONE_SYSTEMS_OF[sport].includes(this.zoneSystem() as ZoneSystem)) {
      this.setZoneSystem('');
    }
  }

  protected setZoneSystem(value: string): void {
    this.zoneSystemValue.set(value);
    this.zoneValue.set('');
  }

  protected submit(): void {
    const errors: Partial<Record<Field, string>> = {};
    const title = checkTitle(this.titleValue());
    const notes = checkNotes(this.notesValue());
    const duration = this.keepsStructure()
      ? { ok: true as const, value: this.start().duration_minutes }
      : parseDuration(this.durationValue());
    const stretching = parseStretching(this.stretchingValue());
    if (title !== null) {
      errors.title = title;
    }
    if (notes !== null) {
      errors.notes = notes;
    }
    if (!duration.ok) {
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
      segments: this.keepsStructure() ? this.start().segments : [],
      // The exercises belong to a strength workout: they stay with it and go with another sport.
      exercises: this.sportValue() === 'strength' ? this.start().exercises : [],
    });
  }
}
