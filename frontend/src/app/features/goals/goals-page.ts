import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { GoalsApi } from '../../core/goals/goals-api';
import { Goal, GoalChanges, GoalStatus } from '../../core/goals/goals-models';
import {
  KIND_LABELS,
  PRIORITY_LABELS,
  STATUS_LABELS,
  daysToGoText,
  describeTarget,
} from './goal-format';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

const FALLBACK = 'Something went wrong. Please try again.';
const GONE = 'That goal does not exist any more.';
const REFRESH_FAILED = 'The list could not be refreshed. Please try again.';

const NOTICES: Record<GoalStatus, string> = {
  active: 'The goal is active again.',
  achieved: 'The goal was marked as achieved.',
  dropped: 'The goal was dropped.',
};

/**
 * The user's goals, with the main goal first. Goals are finished (achieved or dropped) and
 * brought back here; the server decides what is allowed and says why when it is not, for example
 * that there already is a main goal. One action at a time, and the list is fetched again after
 * every change so that it always shows the server's order.
 */
@Component({
  selector: 'app-goals-page',
  imports: [RouterLink, DatePipe],
  templateUrl: './goals-page.html',
  styleUrls: ['../auth/auth-form.css', './goals-page.css'],
})
export class GoalsPage implements OnInit {
  private readonly api = inject(GoalsApi);

  protected readonly view = signal<View>('loading');
  protected readonly goals = signal<Goal[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The id of the goal that is about to be deleted, waiting for the answer to "Are you sure?". */
  protected readonly confirming = signal<string | null>(null);

  protected readonly kindLabel = KIND_LABELS;
  protected readonly priorityLabel = PRIORITY_LABELS;
  protected readonly statusLabel = STATUS_LABELS;
  protected readonly daysText = daysToGoText;
  protected readonly target = describeTarget;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.list();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.goals.set(result.goals);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected setStatus(goal: Goal, status: GoalStatus): Promise<void> {
    return this.change(goal, { status }, NOTICES[status]);
  }

  protected makeMain(goal: Goal): Promise<void> {
    return this.change(goal, { priority: 'main' }, 'The goal is now your main goal.');
  }

  protected makeSecondary(goal: Goal): Promise<void> {
    return this.change(goal, { priority: 'secondary' }, 'The goal is now a secondary goal.');
  }

  protected askDelete(goal: Goal): void {
    this.clearMessages();
    this.confirming.set(goal.id);
  }

  protected cancelDelete(): void {
    this.confirming.set(null);
  }

  protected async delete(goal: Goal): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.delete(goal.id);
      this.confirming.set(null);
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.notice.set(result.kind === 'deleted' ? 'The goal was deleted.' : GONE);
      await this.refresh();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  private async change(goal: Goal, changes: GoalChanges, notice: string): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.clearMessages();
    this.busy.set(true);
    try {
      const result = await this.api.update(goal.id, changes);
      switch (result.kind) {
        case 'ok':
          this.notice.set(notice);
          await this.refresh();
          break;
        case 'invalid':
          this.errors.set(result.errors);
          break;
        case 'not_found':
          this.errors.set([GONE]);
          await this.refresh();
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** Fetches the list again without leaving the page; a failure is shown above the list. */
  private async refresh(): Promise<void> {
    try {
      const result = await this.api.list();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.goals.set(result.goals);
    } catch {
      this.errors.update((list) => [...list, REFRESH_FAILED]);
    }
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
