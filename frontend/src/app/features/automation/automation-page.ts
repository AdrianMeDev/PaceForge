import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { JobsApi } from '../../core/jobs/jobs-api';
import {
  JobCode,
  JobName,
  JobRun,
  JobSettings,
  SettingsChanges,
} from '../../core/jobs/jobs-models';
import { PageHeader } from '../../shared/page-header';
import { weekRange } from '../planning/plan-format';

type View = 'loading' | 'unreachable' | 'signed_out' | 'ready';

const SAVE_FAILED = 'The setting could not be saved. Please try again.';

/** The three jobs, in the order they run, with their title and what they do. */
const JOBS: readonly {
  key: keyof JobSettings;
  name: JobName;
  title: string;
  hint: string;
}[] = [
  {
    key: 'sync',
    name: 'sync',
    title: 'Sync activities',
    hint: 'Pulls new activities from Intervals.icu every day.',
  },
  {
    key: 'week_review',
    name: 'week_review',
    title: 'Week review',
    hint: 'Lets the coach comment on the week that is ending, every Sunday evening.',
  },
  {
    key: 'week_draft',
    name: 'week_draft',
    title: 'Draft next week',
    hint: 'Lets the coach draft the next week, every Sunday evening.',
  },
];

/** What the table says for each job, its outcomes and each reason it did not succeed. */
const JOB_LABELS: Record<JobName, string> = {
  sync: 'Sync activities',
  week_review: 'Week review',
  week_draft: 'Draft next week',
};

const OUTCOME_LABELS: Record<JobRun['outcome'], string> = {
  done: 'Done',
  skipped: 'Skipped',
  failed: 'Failed',
};

/** A fixed sentence for every code; empty code is a run that simply succeeded. */
const CODE_TEXTS: Record<Exclude<JobCode, ''>, string> = {
  not_connected: 'No Intervals.icu connection.',
  invalid_key: 'The Intervals.icu key was refused.',
  intervals_unavailable: 'Intervals.icu did not answer.',
  no_coach: 'No coach configured.',
  provider_error: 'The coach did not answer.',
  plan_not_usable: 'The plan did not pass the checks.',
  comment_not_usable: 'The comment was not usable.',
  no_time: 'No training time known.',
  nothing_to_review: 'Nothing to review.',
  already_planned: 'Next week is already planned.',
  unexpected: 'An unexpected error occurred.',
};

/** The jobs whose switch is waiting for the server; the value is always `true`. */
type Pending = Partial<Record<keyof JobSettings, true>>;

/**
 * Where the athlete turns the three background jobs on or off and reads what each one did. The
 * switches save one flag at a time with PATCH; turning a job off never undoes anything it already
 * did. The log shows the newest runs with a fixed sentence for each reason, never text from the
 * coach or from Intervals.icu.
 */
@Component({
  selector: 'app-automation-page',
  imports: [DatePipe, RouterLink, PageHeader],
  templateUrl: './automation-page.html',
  styleUrl: './automation-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AutomationPage implements OnInit {
  private readonly api = inject(JobsApi);

  protected readonly view = signal<View>('loading');
  protected readonly settings = signal<JobSettings | null>(null);
  protected readonly runs = signal<JobRun[]>([]);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal<string | null>(null);
  /** The job whose switch is being saved: its controls are disabled meanwhile. */
  protected readonly pending = signal<Pending>({});

  protected readonly jobs = JOBS;

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    this.errors.set([]);
    try {
      const settings = await this.api.getSettings();
      if (settings.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.settings.set(settings.settings);
      if (!(await this.loadRuns())) {
        return;
      }
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected isChecked(key: keyof JobSettings): boolean {
    return this.settings()?.[key] ?? false;
  }

  protected isBusy(key: keyof JobSettings): boolean {
    return this.pending()[key] === true;
  }

  protected settingChanged(key: keyof JobSettings, event: Event): void {
    const input = event.target as HTMLInputElement;
    void this.save(key, input.checked, input);
  }

  protected async save(
    key: keyof JobSettings,
    value: boolean,
    input?: HTMLInputElement,
  ): Promise<void> {
    if (this.isBusy(key)) {
      return;
    }
    this.clearMessages();
    const previous = this.settings()?.[key] ?? !value;
    // Optimistic: the switch moves now, and moves back if the save fails.
    this.settings.update((current) => (current ? { ...current, [key]: value } : current));
    this.pending.update((pending) => ({ ...pending, [key]: true }));
    try {
      const changes: SettingsChanges = { [key]: value };
      const result = await this.api.saveSettings(changes);
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      // Only this switch takes the server's answer: another save may be in flight for a
      // different one, and its value must not be overwritten by this response.
      this.settings.update((current) =>
        current ? { ...current, [key]: result.settings[key] } : result.settings,
      );
      this.notice.set('Saved.');
    } catch {
      this.settings.update((current) => (current ? { ...current, [key]: previous } : current));
      if (input) {
        // The binding may not change before the next check, so put the checkbox back itself.
        input.checked = previous;
      }
      this.errors.set([SAVE_FAILED]);
    } finally {
      this.pending.update((pending) => {
        const rest = { ...pending };
        delete rest[key];
        return rest;
      });
    }
  }

  protected jobLabel(run: JobRun): string {
    return JOB_LABELS[run.job] ?? run.job;
  }

  protected outcomeLabel(run: JobRun): string {
    return OUTCOME_LABELS[run.outcome];
  }

  protected weekText(run: JobRun): string {
    return run.week_start === null ? '—' : weekRange(run.week_start);
  }

  protected codeText(run: JobRun): string {
    if (run.code === '') {
      return '';
    }
    return CODE_TEXTS[run.code] ?? run.code;
  }

  protected countsText(run: JobRun): string {
    const counts = Object.entries(run.counts)
      .map(([key, value]) => `${key.replaceAll('_', ' ')} ${value}`)
      .join(', ');
    if (counts === '') {
      return '';
    }
    // After a reason the numbers are an aside; for a plain success they are the whole detail.
    return run.code === '' ? counts : ` (${counts})`;
  }

  /** Loads the log; false when the session has ended (the view is then already `signed_out`). */
  private async loadRuns(): Promise<boolean> {
    const result = await this.api.listRuns();
    if (result.kind === 'forbidden') {
      this.view.set('signed_out');
      return false;
    }
    this.runs.set(result.runs);
    return true;
  }

  private clearMessages(): void {
    this.errors.set([]);
    this.notice.set(null);
  }
}
