import { Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SetupKey, SetupStep } from '../../core/dashboard/dashboard-models';
import { Icon } from '../../shared/icon';

/** What a step says to the user and where its button goes. */
export interface StepInfo {
  title: string;
  text: string;
  link: string;
  action: string;
}

export const STEP_INFO: Record<SetupKey, StepInfo> = {
  profile: {
    title: 'Set your time zone',
    text: 'It decides which day an activity belongs to.',
    link: '/settings/profile',
    action: 'Open the profile',
  },
  training_time: {
    title: 'Say how much time you have',
    text: 'The minutes you can train on each weekday: plans keep to them.',
    link: '/availability',
    action: 'Enter your time',
  },
  ai_coach: {
    title: 'Connect your AI coach',
    text: 'The coach works with your own AI account and key.',
    link: '/settings/connections',
    action: 'Set up the coach',
  },
  intervals: {
    title: 'Connect Intervals.icu',
    text: 'To send planned workouts to your calendar and read your thresholds.',
    link: '/settings/connections',
    action: 'Connect',
  },
  goal: {
    title: 'Add a goal',
    text: 'A race, a threshold target or a general goal: this is what the season works towards.',
    link: '/goals',
    action: 'Add a goal',
  },
  activities: {
    title: 'Import your activities',
    text: 'FIT, TCX or GPX files from your watch, or sessions entered by hand.',
    link: '/activities',
    action: 'Import activities',
  },
  season: {
    title: 'Make a season plan',
    text: 'The skeleton of your season, filled in by your coach. Confirm it to use it.',
    link: '/season',
    action: 'Open the season',
  },
  first_week: {
    title: 'Plan your first week',
    text: 'Let your coach draft a week, read it and confirm it.',
    link: '/planning',
    action: 'Plan a week',
  },
};

/**
 * The steps to set PaceForge up, in order, each ticked off by the data the user has entered (the
 * server works that out). Optional steps are marked and not counted. The page decides when the
 * card is shown; "Hide" only says that the user wants it gone.
 */
@Component({
  selector: 'app-setup-checklist',
  imports: [RouterLink, Icon],
  template: `
    <section class="card" aria-labelledby="setup-heading" data-testid="setup">
      <div class="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="setup-heading" class="m-0 text-lg font-semibold">Get started</h2>
          <p class="m-0 text-muted" data-testid="setup-count">
            {{ doneCount() }} of {{ requiredCount() }} done
          </p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" (click)="hide.emit()">Hide</button>
      </div>
      <ol class="m-0 grid list-none gap-3 p-0">
        @for (step of steps(); track step.key; let index = $index) {
          <li
            class="flex items-start gap-3"
            [attr.data-testid]="'setup-' + step.key"
            [attr.data-done]="step.done"
          >
            <span
              class="grid size-7 flex-none place-items-center rounded-full border border-border text-sm"
              [class.bg-accent]="step.done"
              [class.text-accent-text]="step.done"
              aria-hidden="true"
            >
              @if (step.done) {
                <app-icon name="check" />
              } @else {
                {{ index + 1 }}
              }
            </span>
            <div class="min-w-0 flex-1">
              <p class="m-0 font-semibold">
                {{ info[step.key].title }}
                @if (step.optional) {
                  <span class="badge ml-1 text-muted font-normal">optional</span>
                }
                <span class="sr-only">{{ step.done ? ' (done)' : ' (to do)' }}</span>
              </p>
              <p class="m-0 text-sm text-muted">{{ info[step.key].text }}</p>
              @if (!step.done) {
                <a
                  class="btn btn-secondary btn-sm mt-2 no-underline"
                  [routerLink]="info[step.key].link"
                  >{{ info[step.key].action }}</a
                >
              }
            </div>
          </li>
        }
      </ol>
    </section>
  `,
})
export class SetupChecklist {
  readonly steps = input.required<SetupStep[]>();
  readonly hide = output<void>();

  protected readonly info = STEP_INFO;
  private readonly required = computed(() => this.steps().filter((step) => !step.optional));
  protected readonly requiredCount = computed(() => this.required().length);
  protected readonly doneCount = computed(() => this.required().filter((step) => step.done).length);
}

/** Where the browser remembers that the user hid the card (per browser, not per account). */
export const HIDDEN_KEY = 'paceforge.setup.hidden';

export function readHidden(): boolean {
  try {
    return globalThis.localStorage.getItem(HIDDEN_KEY) === '1';
  } catch {
    return false; // no storage (private window, blocked): the card is simply shown
  }
}

export function writeHidden(hidden: boolean): void {
  try {
    if (hidden) {
      globalThis.localStorage.setItem(HIDDEN_KEY, '1');
    } else {
      globalThis.localStorage.removeItem(HIDDEN_KEY);
    }
  } catch {
    // the choice is kept for this visit only
  }
}

/** Whether every step that is not optional is done. */
export function setupComplete(steps: SetupStep[]): boolean {
  return steps.filter((step) => !step.optional).every((step) => step.done);
}
