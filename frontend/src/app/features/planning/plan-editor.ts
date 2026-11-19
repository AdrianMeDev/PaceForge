import {
  Component,
  OnInit,
  computed,
  inject,
  input,
  linkedSignal,
  output,
  signal,
} from '@angular/core';
import { PlanningApi } from '../../core/planning/planning-api';
import {
  EditedPlan,
  EditedWorkout,
  Finding,
  PlanProblem,
  WeekPlan,
} from '../../core/planning/planning-models';
import { EditorDay, editorDays, editedFrom } from './edit-format';
import {
  GOAL_LABELS,
  SLOT_LABELS,
  SPORT_ICONS,
  SPORT_LABELS,
  minutesText,
  segmentText,
  stretchingText,
  targetText,
} from './plan-format';
import { Icon } from '../../shared/icon';
import { WorkoutForm } from './workout-form';

const FALLBACK = 'Something went wrong. Please try again.';
const CHECK_FAILED = 'The checks could not be run. Please try again.';
const NOT_PLANNABLE = 'This week cannot be planned any more, so it cannot be changed.';
const NOT_REVISABLE = 'This plan cannot be changed any more. Open the current version of the week.';
const GONE = 'That plan does not exist any more.';
const NOT_READABLE = 'The plan cannot be read:';

/** What is being edited: the workout at an index of the list, a new one, or nothing. */
type Editing = number | 'new' | null;

/**
 * Change a plan by hand: edit, move, remove or add workouts, with the checks of the server after
 * every change, and store the result as a new version of the week. Nothing is stored before
 * "Save as a new version": until then the changes are only in this component, and the version they
 * started from is not touched. A plan with errors can be saved too (the user sees what is wrong);
 * it cannot be confirmed.
 *
 * The checks of the server number the workouts as they are stored (by day and time of day) and
 * answer with `order`, which says where each of them is in the list that was sent. An answer that
 * arrives after a newer change is dropped, so that what is shown always belongs to what is on the
 * screen, and nothing about a workout is shown while a check is under way.
 */
@Component({
  selector: 'app-plan-editor',
  imports: [Icon, WorkoutForm],
  templateUrl: './plan-editor.html',
  styleUrl: './plan-editor.css',
})
export class PlanEditor implements OnInit {
  private readonly api = inject(PlanningApi);

  /** The plan that is changed: a draft or a confirmed plan. */
  readonly plan = input.required<WeekPlan>();
  /** The new draft was stored. */
  readonly saved = output<WeekPlan>();
  /** The user leaves without saving. */
  readonly cancelled = output<void>();
  readonly signedOut = output<void>();

  protected readonly workouts = linkedSignal<EditedWorkout[]>(() =>
    this.plan().workouts.map(editedFrom),
  );
  protected readonly editing = signal<Editing>(null);
  protected readonly findings = signal<Finding[]>([]);
  protected readonly order = signal<number[]>([]);
  protected readonly checking = signal(false);
  protected readonly saving = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly problems = signal<PlanProblem[]>([]);

  /** The number of the latest check; an answer of an earlier one is not used. */
  private checks = 0;

  protected readonly days = computed<EditorDay[]>(() => editorDays(this.workouts()));
  protected readonly changed = computed(
    () => JSON.stringify(this.workouts()) !== JSON.stringify(this.plan().workouts.map(editedFrom)),
  );
  protected readonly weekFindings = computed(() =>
    this.findings().filter((finding) => !/^workouts\[/.test(finding.path)),
  );
  protected readonly errors = computed(
    () => this.findings().filter((finding) => finding.severity === 'error').length,
  );
  protected readonly notes = computed(() => this.findings().length - this.errors());

  protected readonly sport = SPORT_LABELS;
  protected readonly icon = SPORT_ICONS;
  protected readonly goal = GOAL_LABELS;
  protected readonly slot = SLOT_LABELS;
  protected readonly minutes = minutesText;
  protected readonly stretching = stretchingText;
  protected readonly target = targetText;
  protected readonly segment = segmentText;

  ngOnInit(): void {
    // The first check is of the plan as it is: the user sees where it stands before changing it.
    void this.check();
  }

  /** The findings that name the workout at `index` of the list. */
  protected findingsOf(index: number): Finding[] {
    const order = this.order();
    return this.findings().filter((finding) => {
      const match = /^workouts\[(\d+)\]/.exec(finding.path);
      return match !== null && order[Number(match[1])] === index;
    });
  }

  protected change(index: number): void {
    this.editing.set(index);
  }

  protected add(): void {
    this.editing.set('new');
  }

  protected closeForm(): void {
    this.editing.set(null);
  }

  protected remove(index: number): void {
    this.workouts.update((list) => list.filter((_, place) => place !== index));
    this.editing.set(null);
    void this.check();
  }

  protected workoutSaved(workout: EditedWorkout): void {
    const editing = this.editing();
    if (editing === 'new') {
      this.workouts.update((list) => [...list, workout]);
    } else if (editing !== null) {
      this.workouts.update((list) => list.map((old, place) => (place === editing ? workout : old)));
    }
    this.editing.set(null);
    void this.check();
  }

  protected async save(): Promise<void> {
    if (this.saving() || this.editing() !== null || !this.changed()) {
      return;
    }
    this.message.set(null);
    this.problems.set([]);
    this.saving.set(true);
    try {
      const result = await this.api.revise(this.plan().id, this.body());
      switch (result.kind) {
        case 'ok':
          this.saved.emit(result.plan);
          break;
        case 'invalid':
          this.message.set(NOT_READABLE);
          this.problems.set(result.problems);
          break;
        case 'not_plannable':
          this.message.set(NOT_PLANNABLE);
          break;
        case 'not_revisable':
          this.message.set(NOT_REVISABLE);
          break;
        case 'not_found':
          this.message.set(GONE);
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

  /** Asks the server what it thinks of the plan as it is on the screen now. */
  protected async check(): Promise<void> {
    const mine = ++this.checks;
    this.checking.set(true);
    this.message.set(null);
    this.problems.set([]);
    try {
      const result = await this.api.check(this.plan().week_start, this.body());
      if (mine !== this.checks) {
        return;
      }
      switch (result.kind) {
        case 'ok':
          this.findings.set(result.report.findings);
          this.order.set(result.order);
          return;
        case 'not_plannable':
          this.message.set(NOT_PLANNABLE);
          break;
        case 'invalid':
          this.message.set(NOT_READABLE);
          this.problems.set(result.problems);
          break;
        case 'forbidden':
          this.signedOut.emit();
          break;
      }
      this.findings.set([]);
    } catch {
      if (mine === this.checks) {
        this.findings.set([]);
        this.message.set(CHECK_FAILED);
      }
    } finally {
      if (mine === this.checks) {
        this.checking.set(false);
      }
    }
  }

  private body(): EditedPlan {
    const plan = this.plan();
    return { week_start: plan.week_start, rationale: plan.rationale, workouts: this.workouts() };
  }
}
